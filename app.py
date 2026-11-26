import sqlite3
from datetime import datetime
from hashlib import sha256
from platform import python_version
from uuid import uuid4

import streamlit as st

from src.smartaccess import database, history
from src.smartaccess.config import CAPTURES_REQUIRED, SFACE, YOLO11N, YUNET, Settings
from src.smartaccess.counting import CountingRun
from src.smartaccess.crossing import CountingLine
from src.smartaccess.faces import REFERENCE_METHOD, FaceError, FaceQuality, build_reference, get_face_extractor
from src.smartaccess.media import MediaError
from src.smartaccess.preview import FacePreview
from src.smartaccess.verification import verify

HOME = "Accueil"
PEOPLE = "Personnes"
VERIFY = "Vérifier un accès"
COUNT = "Compter les passages"
HISTORY = "Historique"
PAGES = [HOME, PEOPLE, VERIFY, COUNT, HISTORY]
READY = "Prêt pour la vérification"
PENDING = "Visage à enregistrer"
CAMERA_STATUS = {
    "stopped": "Caméra arrêtée", "opening": "Ouverture en cours",
    "active": "Caméra active", "unavailable": "Caméra indisponible",
}
FACE_GUIDANCE = {
    FaceQuality.NO_FACE: "Placez votre visage devant la caméra",
    FaceQuality.MULTIPLE: "Une seule personne doit être visible",
    FaceQuality.TOO_SMALL: "Rapprochez-vous",
    FaceQuality.BLURRY: "Stabilisez votre position",
    FaceQuality.USABLE: "Visage détecté, vous pouvez capturer",
}


def show_error(message, detail):
    st.error(message)
    with st.expander("Détails techniques"):
        st.text(str(detail))


def stop_cameras_on_leave():
    run = st.session_state.get("counting_run")
    if run is not None and st.session_state.page != COUNT and run.snapshot().status == "running":
        run.stop()
    preview = st.session_state.get("face_preview")
    owner = st.session_state.get("face_preview_owner")
    if preview is not None and owner[0] != st.session_state.page:
        preview.stop()


def navigate(page, user_id=None):
    if user_id is not None:
        st.session_state["person_to_open"] = (page, user_id)
    st.session_state.page = page
    stop_cameras_on_leave()


def face_files_present(settings):
    return all(settings.model_path(name).is_file() for name in (YUNET, SFACE))


def person_status(has_reference):
    return READY if has_reference else PENDING


def home(settings):
    st.write("SmartAccess permet de simuler une vérification d’accès par le visage et de compter les passages devant une caméra.")
    with st.container(horizontal=True):
        st.button("Ajouter une personne", type="primary", on_click=navigate, args=(PEOPLE,))
        st.button(VERIFY, on_click=navigate, args=(VERIFY,))
        st.button(COUNT, on_click=navigate, args=(COUNT,))

    users = database.list_users(settings.database)
    references = [database.reference_count(settings.database, user_id) for user_id in users]
    face_files = face_files_present(settings)
    count_file = settings.model_path(YOLO11N).is_file()
    has_events = bool(history.events(settings.database, limit=1))

    with st.container(border=True):
        st.subheader("Pour commencer")
        if not users:
            st.write("Ajoutez une personne avec son nom ou son pseudonyme.")
        elif not any(references) and not face_files:
            st.write("Installez les modèles de visage pour pouvoir enregistrer une personne. Le guide se trouve dans docs/enregistrement.md.")
        elif not any(references):
            st.write("Ouvrez Personnes, sélectionnez une personne et enregistrez son visage.")
        elif face_files and not history.events(settings.database, kind="verification", limit=1):
            st.write("Ouvrez Vérifier un accès et essayez une première vérification avec une personne prête.")
        elif count_file and not history.events(settings.database, kind="passage", limit=1):
            st.write("Ouvrez Compter les passages et choisissez une vidéo locale ou la caméra intégrée.")
        elif has_events:
            st.write("Ouvrez Historique pour consulter les événements enregistrés.")
            st.button("Voir l’historique", on_click=navigate, args=(HISTORY,))
        else:
            st.write("Installez un modèle pour lancer une vérification ou un comptage. Les guides se trouvent dans le dossier docs.")

    st.subheader("Disponibilité")
    for label, status in (
        ("Modèles de visage disponibles", "Fichiers présents" if face_files else "Fichiers manquants"),
        ("Modèle de comptage disponible", "Fichier présent" if count_file else "Fichier manquant"),
        ("Historique accessible", "Oui"),
    ):
        st.markdown(f"**{label}** · {status}")
    st.caption("La présence des fichiers est vérifiée ici. Les modèles sont chargés à l’utilisation.")
    if not settings.test_video.is_file():
        st.caption("Aucune vidéo locale disponible. Vous pouvez compter les passages avec la caméra intégrée.")
        st.button("Ouvrir le comptage", on_click=navigate, args=(COUNT,))
    if not has_events:
        st.caption("L’historique est vide. Lancez une vérification ou faites franchir la ligne pendant un comptage pour créer un premier événement.")

    with st.expander("Chemins et diagnostics"):
        st.text(f"Base locale : {settings.database}\n"
                f"Vidéo configurée : {settings.test_video}\n"
                f"Caméra locale : index {settings.camera_index}\n"
                f"Python : {python_version()}\nStreamlit : {st.__version__}")
        for model in (YUNET, SFACE, YOLO11N):
            path = settings.model_path(model)
            st.text(f"{path} — {'présent' if path.is_file() else 'absent'}")


def select_person(page, users, references):
    key = f"person_{page}"
    selections = st.session_state.person_selections
    target = st.session_state.get("person_to_open")
    if target and target[0] == page:
        selections[page] = target[1]
        del st.session_state.person_to_open
        st.session_state[key] = selections[page] if selections[page] in users else None
    elif key not in st.session_state:
        st.session_state[key] = selections.get(page) if selections.get(page) in users else None
    elif st.session_state[key] is not None and st.session_state[key] not in users:
        st.session_state[key] = None
    user_id = st.selectbox(
        "Sélectionner une personne", list(users), index=None, key=key,
        placeholder="Choisissez une personne",
        format_func=lambda user_id: f"{users[user_id]} (n° {user_id}) · {person_status(references[user_id])}",
    )
    selections[page] = user_id
    preview = st.session_state.get("face_preview")
    if preview is not None and st.session_state.face_preview_owner != (page, user_id):
        preview.stop()
    return user_id


def freeze_photo(owner, preview, frame):
    if st.session_state.face_preview_owner != owner or preview.stopping:
        return
    st.session_state.face_photos[owner] = frame
    preview.stop()


def render_live_camera(preview, owner, polling):
    if owner in st.session_state.face_photos:
        st.rerun()
    state = preview.snapshot()
    if polling and state.status not in ("opening", "active"):
        st.rerun()

    st.write(f"**{CAMERA_STATUS[state.status]}**")
    if state.error:
        if state.error_source == "camera":
            message = "Fermez les autres applications qui utilisent la caméra, vérifiez les autorisations Windows, puis réessayez."
        elif state.error_source == "model":
            message = "Les modèles de visage n’ont pas pu être chargés. Vérifiez leur installation, puis réessayez."
        else:
            message = "L’image n’a pas pu être analysée. Redémarrez la caméra pour réessayer."
        show_error(message, state.error)

    if polling:
        preview.heartbeat()
        st.button("Arrêter la caméra", disabled=preview.stopping, on_click=preview.stop)
        if preview.stopping:
            st.caption("Arrêt en cours…")
        elif state.frame is not None:
            frame = state.frame
            st.image(frame.annotated(), channels="BGR", width=720, alt="Aperçu de la caméra avec les cadres YuNet")
            st.write(FACE_GUIDANCE[frame.assessment.quality])
            st.button(
                "Prendre une photo", type="primary", disabled=frame.assessment.quality is not FaceQuality.USABLE,
                on_click=freeze_photo, args=(owner, preview, frame),
            )


def face_camera(settings, owner):
    preview = st.session_state.get("face_preview")
    same_owner = st.session_state.get("face_preview_owner") == owner
    running = preview is not None and preview.snapshot().status in ("opening", "active")
    if running or (preview is not None and same_owner):
        st.fragment(render_live_camera, run_every=0.2 if running else None)(preview, owner, running)
    else:
        st.write("**Caméra arrêtée**")

    if not running:
        available = face_files_present(settings)
        if not available:
            show_error("Installez les modèles de visage avant de démarrer la caméra.", settings.models)
        if st.button("Démarrer la caméra", type="primary", disabled=not available):
            preview = FacePreview(settings)
            st.session_state.face_preview = preview
            st.session_state.face_preview_owner = owner
            preview.start()
            st.rerun()


def show_frozen_photo(frame, owner):
    preview = st.session_state.get("face_preview")
    if preview is not None and st.session_state.face_preview_owner == owner:
        stopping = preview.snapshot().status in ("opening", "active")

        @st.fragment(run_every=0.2 if stopping else None)
        def camera_status():
            if stopping and preview.snapshot().status not in ("opening", "active"):
                st.rerun()
            st.caption("Arrêt en cours…" if stopping else "Caméra arrêtée")

        camera_status()
    st.image(frame.annotated(), channels="BGR", width=720, caption="Photo capturée",
             alt="Photo sélectionnée pour l’analyse, avec le cadre YuNet")


def people_page(settings):
    st.subheader("1. Créer ou sélectionner une personne")
    with st.form("new_user", clear_on_submit=True):
        name = st.text_input("Nom ou pseudonyme")
        if st.form_submit_button("Créer la personne", type="primary"):
            try:
                user_id = database.create_user(settings.database, name)
            except ValueError:
                st.error("Saisissez un nom ou un pseudonyme.")
            else:
                st.session_state.person_to_open = (PEOPLE, user_id)
                st.rerun()

    users = database.list_users(settings.database)
    if not users:
        st.info("La liste est vide. Créez une personne pour enregistrer son visage.")
        return

    references = {user_id: database.reference_count(settings.database, user_id) for user_id in users}
    st.dataframe(
        [{"Nom": name, "Statut": person_status(references[user_id])} for user_id, name in users.items()],
        hide_index=True, alt="Personnes et état de leur enregistrement facial",
    )
    user_id = select_person(PEOPLE, users, references)
    if user_id is None:
        return

    enrollment(settings, user_id, references[user_id])
    with st.expander("Supprimer cette personne"):
        confirmed = st.checkbox(
            "Je confirme la suppression de cette personne et de sa référence faciale.",
            key=f"delete_{user_id}",
        )
        if st.button("Confirmer la suppression", disabled=not confirmed):
            deleted = database.delete_user(settings.database, user_id)
            st.session_state.enrollment_drafts.pop(user_id, None)
            st.session_state.verifications.pop(user_id, None)
            st.session_state.face_photos.pop((PEOPLE, user_id), None)
            st.session_state.face_photos.pop((VERIFY, user_id), None)
            preview = st.session_state.get("face_preview")
            if preview is not None:
                preview.stop()
            if deleted:
                st.session_state.person_deleted = True
            st.rerun()


def enrollment(settings, user_id, saved_count):
    st.subheader("2. Enregistrer le visage")
    drafts = st.session_state.enrollment_drafts
    owner = (PEOPLE, user_id)
    photos = st.session_state.face_photos
    replacing = user_id in drafts
    if saved_count is not None and not replacing:
        st.caption("Le visage est déjà enregistré.")
        if st.button("Refaire l’enregistrement"):
            drafts[user_id] = {}
            st.rerun()
    else:
        samples = drafts.get(user_id, {})
        st.progress(len(samples) / CAPTURES_REQUIRED, text=f"{len(samples)} captures sur {CAPTURES_REQUIRED}")
        if saved_count is not None:
            st.caption("La référence actuelle sera remplacée après l’enregistrement des nouvelles captures.")
        if len(samples) < CAPTURES_REQUIRED:
            st.write("Avec l’accord de la personne, placez-la seule face à la caméra, visage bien visible et bien éclairé.")
            st.caption("Si une photo est rejetée, corrigez le cadrage ou l’éclairage puis reprenez-la. Les captures valides sont conservées.")
            frame = photos.get(owner)
            if frame is None:
                face_camera(settings, owner)
            else:
                show_frozen_photo(frame, owner)
                with st.container(horizontal=True):
                    accept = st.button("Utiliser cette photo", type="primary")
                    retake = st.button("Reprendre la photo")
                if retake:
                    photos.pop(owner)
                    st.rerun()
                if accept:
                    with st.spinner("Validation de la photo…"):
                        try:
                            content = frame.photo()
                            digest = sha256(content).digest()
                            if digest in samples:
                                raise FaceError("Cette photo a déjà été ajoutée.")
                            samples[digest] = get_face_extractor(settings).extract(content)
                        except (FaceError, MediaError) as exc:
                            show_error("Photo inutilisable. Reprenez la photo avant de continuer.", exc)
                        else:
                            drafts[user_id] = samples
                            photos.pop(owner)
                            st.rerun()

        if len(samples) == CAPTURES_REQUIRED and st.button("Enregistrer le visage", type="primary"):
            try:
                reference = build_reference(list(samples.values()))
                database.save_reference(settings.database, user_id, reference, SFACE, REFERENCE_METHOD, len(samples))
            except (FaceError, sqlite3.Error) as exc:
                show_error("Le visage n’a pas été enregistré. Réessayez ou recommencez les captures.", exc)
            else:
                drafts.pop(user_id)
                st.session_state.verifications.pop(user_id, None)
                st.rerun()

        if replacing and st.button("Annuler les captures"):
            drafts.pop(user_id)
            photos.pop(owner, None)
            preview = st.session_state.get("face_preview")
            if preview is not None:
                preview.stop()
            st.rerun()

    if saved_count is not None and not replacing:
        st.subheader("3. Confirmation")
        st.success(f"Visage enregistré avec {saved_count} captures. La personne est prête pour la vérification.")
        st.button("Vérifier cette personne", type="primary", on_click=navigate, args=(VERIFY, user_id))


def verification_page(settings):
    st.caption("L’ouverture est simulée. Une photo ou une vidéo présentée à la caméra peut tromper la vérification.")
    users = database.list_users(settings.database)
    if not users:
        st.info("Ajoutez une personne et enregistrez son visage pour pouvoir vérifier un accès.")
        st.button("Ajouter une personne", on_click=navigate, args=(PEOPLE,))
        return

    references = {user_id: database.reference_count(settings.database, user_id) for user_id in users}
    user_id = select_person(VERIFY, users, references)
    if user_id is None:
        st.caption("Choisissez la personne dont vous souhaitez vérifier l’accès.")
        return
    if not references[user_id]:
        st.info("Le visage de cette personne doit être enregistré avant la vérification.")
        st.button("Enregistrer son visage", on_click=navigate, args=(PEOPLE, user_id))
        return

    attempts = st.session_state.verifications
    owner = (VERIFY, user_id)
    photos = st.session_state.face_photos
    attempt = attempts.get(user_id)
    if attempt and "result" in attempt:
        render_result(attempt["result"])
        with st.container(horizontal=True):
            if st.button("Nouvelle vérification", type="primary"):
                attempts.pop(user_id)
                st.rerun()
            st.button("Voir l’historique", on_click=navigate, args=(HISTORY,))
        return

    frame = photos.get(owner)
    if frame is None:
        st.subheader("Prendre une photo")
        st.write("Placez la personne seule face à la caméra, visage visible et bien éclairé.")
        face_camera(settings, owner)
        return

    st.subheader("Lancer la vérification")
    show_frozen_photo(frame, owner)
    st.caption("Lancez la comparaison avec le visage enregistré.")
    models_available = face_files_present(settings)
    if not models_available:
        show_error("Installez les modèles de visage avant de lancer une vérification.", settings.models)
    with st.container(horizontal=True):
        launch = st.button("Lancer la vérification", type="primary", disabled=not models_available)
        retake = st.button("Reprendre la photo")
    if retake:
        photos.pop(owner)
        attempts.pop(user_id, None)
        st.rerun()
    if launch:
        with st.spinner("Vérification en cours…"):
            if attempt is None:
                attempt = {"request_id": uuid4().hex}
                attempts[user_id] = attempt
            try:
                result = verify(settings, user_id, attempt["request_id"], frame.photo())
            except MediaError as exc:
                show_error("La photo est inutilisable. Reprenez-la avant de continuer.", exc)
            except FaceError as exc:
                show_error("Les modèles de visage n’ont pas pu être chargés. Vérifiez leur installation, puis réessayez.", exc)
            except ValueError as exc:
                show_error("La référence faciale est indisponible ou incompatible. Réenregistrez le visage dans Personnes.", exc)
                st.button("Ouvrir cette personne", on_click=navigate, args=(PEOPLE, user_id))
            except sqlite3.Error as exc:
                show_error("La tentative n’a pas pu être confirmée dans l’historique. Réessayez avec la même photo.", exc)
            else:
                attempts[user_id] = {"result": result}
                photos.pop(owner)
                st.rerun()


def render_result(result):
    attempt = result.attempt
    if attempt.outcome == "authorized":
        st.success("La vérification est terminée. Vous pouvez consulter la tentative dans l’historique.",
                   title="Accès autorisé — simulation")
    elif attempt.outcome == "denied":
        st.error("Vérifiez la personne sélectionnée avant de lancer une nouvelle vérification.", title="Accès refusé")
    else:
        st.warning("Lancez une nouvelle vérification avec une seule personne, de face et bien éclairée.",
                   title="Photo à reprendre")
    with st.expander("Détails du résultat"):
        if attempt.similarity is not None:
            st.write(f"Score de similarité cosinus · {attempt.similarity:.6g}")
        else:
            st.write("Score de similarité indisponible.")
        if attempt.threshold is not None:
            st.write(f"Seuil d’autorisation · {attempt.threshold:.6g}")
    if result.capture_error:
        with st.expander("Détails techniques"):
            st.text(result.capture_error)


def render_counting_run(run, polling):
    run.heartbeat()
    progress = run.snapshot()
    if polling and progress.status != "running":
        st.rerun()
    if progress.status == "running":
        if st.button("Arrêter", disabled=run.stopping):
            run.stop()
        if run.stopping:
            st.caption("Arrêt en cours…")
        elif run.webcam:
            st.write(f"**{CAMERA_STATUS['active' if progress.frames else 'opening']}**")
        else:
            st.caption("Analyse en cours…")
    elif progress.status == "error":
        if progress.error_source == "model":
            message = "Le modèle de comptage n’a pas pu être chargé. Vérifiez son installation, puis réessayez."
        elif progress.error_source == "media" and run.webcam:
            message = "Caméra indisponible. Vérifiez les autorisations et fermez les autres applications caméra, puis réessayez."
        elif progress.error_source == "media":
            message = "Vidéo illisible. Vérifiez que le fichier s’ouvre ou configurez une autre vidéo, puis réessayez."
        else:
            message = "Le comptage a été interrompu. Consultez les détails, puis réessayez."
        show_error(message, progress.error)
    elif progress.status == "stopped":
        st.info("Comptage arrêté. Les passages enregistrés sont conservés.")
    else:
        st.success("Analyse de la vidéo terminée.")

    entries, exits = st.columns(2)
    entries.metric("Entrées", progress.entries)
    exits.metric("Sorties", progress.exits)
    if progress.image is not None:
        st.image(progress.image, channels="BGR", width=720,
                 alt="Personnes suivies avec leurs identifiants, ligne et sens de franchissement")
        entry, exit_ = ("↓", "↑") if run.line.entry_down else ("↑", "↓")
        st.caption(f"Entrée {entry} · Sortie {exit_} · Les identifiants correspondent au suivi pendant cette session.")
    with st.expander("Détails de la session"):
        st.text(f"Session : {run.session_id}\nImages traitées : {progress.frames}\nDébit : {progress.fps:.1f} images/s")


def counting_page(settings):
    run = st.session_state.get("counting_run")
    running = run is not None and run.snapshot().status == "running"
    source = st.radio(
        "Source", ["Vidéo locale", "Caméra intégrée"],
        key="count_source", disabled=running,
    )
    webcam = source == "Caméra intégrée"
    available = webcam or settings.test_video.is_file()
    weights_present = settings.model_path(YOLO11N).is_file()
    if not available:
        st.info("Aucune vidéo locale disponible. Choisissez la caméra intégrée ou configurez une vidéo.")
    if not weights_present:
        show_error("Installez le modèle de comptage avant de démarrer. Le guide se trouve dans docs/comptage.md.",
                   settings.model_path(YOLO11N))

    defaults = CountingLine()
    with st.expander("Réglages avancés"):
        y = st.slider("Position de la ligne depuis le haut (%)", 5, 95, round(defaults.y * 100), disabled=running)
        tolerance = st.slider("Marge de chaque côté (%)", 1, 20, round(defaults.tolerance * 100), disabled=running)
        entry_down = st.selectbox("Sens de l’entrée", [True, False], disabled=running,
                                  format_func=lambda down: "Du haut vers le bas" if down else "Du bas vers le haut")
        st.text(f"Vidéo locale : {settings.test_video}\nCaméra locale : index {settings.camera_index}")

    st.caption(
        f"{'Pour le prochain comptage, la' if run is not None and not running else 'La'} "
        f"ligne jaune se situe à {y} % de la hauteur de l’image depuis le haut. "
        f"Une entrée est un franchissement {'du haut vers le bas' if entry_down else 'du bas vers le haut'}. "
        "Gardez les pieds des personnes visibles."
    )
    if not running and st.button("Démarrer", type="primary", disabled=not available or not weights_present):
        try:
            line = CountingLine(y / 100, tolerance / 100, entry_down)
        except ValueError as exc:
            show_error("Rapprochez la ligne du centre ou réduisez la marge dans les réglages avancés.", exc)
        else:
            run = CountingRun(settings, line, webcam=webcam)
            run.start()
            st.session_state.counting_run = run
            st.rerun()
    if run is not None:
        st.fragment(render_counting_run, run_every=0.25 if running else None)(run, running)


def history_page(settings):
    st.write("Consultez les tentatives d’accès ou les passages enregistrés.")
    kind = st.selectbox(
        "Type d’événement", ["verification", "passage"],
        format_func=lambda value: "Tentatives d’accès" if value == "verification" else "Passages",
    )
    verification = kind == "verification"
    outcomes = ("authorized", "denied", "invalid_capture") if verification else ("entry", "exit")
    outcome = st.selectbox("Résultat" if verification else "Sens du passage", [None, *outcomes],
                           key=f"history_outcome_{kind}", format_func=lambda value: history.OUTCOMES.get(value, "Tous"))
    session = None
    if not verification:
        session = st.selectbox("Session de comptage", [None, *history.sessions(settings.database)],
                               format_func=lambda value: value or "Toutes")
    left, right = st.columns(2)
    start = left.date_input("Du (UTC)", value=None, format="DD/MM/YYYY")
    end = right.date_input("Au (UTC)", value=None, format="DD/MM/YYYY")
    if start and end and start > end:
        st.error("Choisissez une date de fin égale ou postérieure à la date de début.")
        return
    rows = history.events(settings.database, kind=kind, outcome=outcome, session=session, start=start, end=end)
    if not rows:
        if history.events(settings.database, kind=kind, limit=1):
            st.info("Aucun événement ne correspond aux filtres. Modifiez les filtres pour élargir la recherche.")
        elif verification:
            st.info("Aucune tentative enregistrée. Lancez une vérification pour créer le premier événement.")
            st.button(VERIFY, on_click=navigate, args=(VERIFY,))
        else:
            st.info("Aucun passage enregistré. Démarrez un comptage et faites franchir la ligne à une personne.")
            st.button(COUNT, on_click=navigate, args=(COUNT,))
        return

    display_rows = []
    for row in rows:
        display_row = row.copy()
        try:
            display_row["Date UTC"] = datetime.fromisoformat(row["Date UTC"]).strftime("%d/%m/%Y %H:%M:%S")
        except ValueError:
            pass
        display_rows.append(display_row)
    columns = (
        ["Date UTC", "Résultat", "Compte", "Similarité", "Seuil"] if verification
        else ["Date UTC", "Résultat", "Session", "ID de suivi"]
    )
    st.caption(f"{len(rows)} événement{'s' if len(rows) > 1 else ''}")
    st.dataframe(display_rows, column_order=columns, hide_index=True, alt="Événements correspondant aux filtres",
                 column_config={"Compte": "N° de personne", "Similarité": "Score de similarité"})
    st.download_button("Exporter les résultats en CSV", history.csv_bytes(rows), "smartaccess-historique.csv",
                       mime="text/csv", on_click="ignore")


def main():
    st.set_page_config(page_title="SmartAccess", page_icon=":material/door_front:")
    try:
        settings = Settings()
        database.initialize(settings.database)
    except ValueError as exc:
        show_error("La configuration de SmartAccess est invalide. Vérifiez les réglages de lancement.", exc)
        return
    except (OSError, sqlite3.Error) as exc:
        show_error("L’historique est inaccessible. Vérifiez les droits d’accès au dossier de données.", exc)
        return

    st.session_state.setdefault("enrollment_drafts", {})
    st.session_state.setdefault("verifications", {})
    st.session_state.setdefault("person_selections", {})
    st.session_state.setdefault("face_photos", {})
    st.sidebar.title("SmartAccess")
    page = st.sidebar.radio("Pages", PAGES, key="page", on_change=stop_cameras_on_leave)
    st.header(page)
    if page == PEOPLE and st.session_state.pop("person_deleted", False):
        st.success("Personne supprimée.")
    try:
        {
            HOME: home, PEOPLE: people_page, VERIFY: verification_page,
            COUNT: counting_page, HISTORY: history_page,
        }[page](settings)
    except sqlite3.Error as exc:
        show_error("Les données sont momentanément inaccessibles. Réessayez après avoir vérifié l’accès à la base locale.", exc)


if __name__ == "__main__":
    main()
