from contextlib import contextmanager
from threading import Event
from time import sleep
from types import SimpleNamespace

import cv2
import numpy as np
from streamlit.testing.v1 import AppTest

from src.smartaccess import database, faces, preview, verification
from src.smartaccess.config import CAPTURES_REQUIRED, ROOT, SFACE, YUNET


def click(app, label):
    return next(button for button in app.button if button.label == label).click().run()


def start_camera(app, released):
    released.clear()
    click(app, "Démarrer la caméra")
    for _ in range(50):
        if app.session_state.face_preview.snapshot().status == "active":
            break
        sleep(0.01)
    app.run()
    assert any("Caméra active" in item.value for item in app.markdown)
    assert any("Visage détecté, vous pouvez capturer" in item.value for item in app.markdown)


def capture(app, released):
    start_camera(app, released)
    frame = app.session_state.face_preview.snapshot().frame
    click(app, "Prendre une photo")
    assert released.wait(2)
    assert app.image[0].captions == ["Photo capturée"]
    return frame


def test_user_verification_history_and_delete(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("SMARTACCESS_DB", str(path))
    monkeypatch.setenv("SMARTACCESS_MODELS", str(tmp_path))
    monkeypatch.setenv("SMARTACCESS_VIDEO", str(tmp_path / "absente.mp4"))
    monkeypatch.setenv("SMARTACCESS_VERIFICATION_THRESHOLD", "0.363")
    for filename in (YUNET, SFACE):
        (tmp_path / filename).touch()
    released = Event()
    opened = []

    @contextmanager
    def open_camera(index):
        opened.append(index)
        try:
            yield np.full((120, 160, 3), len(opened), dtype=np.uint8)
        finally:
            released.set()

    def frames(image):
        while True:
            yield image
            sleep(0.01)

    monkeypatch.setattr(preview, "open_capture", open_camera)
    monkeypatch.setattr(preview, "frames", frames)
    embedding = np.eye(1, 128, dtype=np.float32)[0]
    received = []

    def extract(photo):
        received.append(cv2.imdecode(np.frombuffer(photo, dtype=np.uint8), cv2.IMREAD_COLOR))
        return embedding

    extractor = SimpleNamespace(
        extract=extract,
        assess=lambda image: faces.FaceAssessment(faces.FaceQuality.USABLE, ((10, 10, 120, 115),)),
    )
    monkeypatch.setattr(faces, "get_face_extractor", lambda settings: extractor)
    monkeypatch.setattr(preview, "get_face_extractor", lambda settings: extractor)
    monkeypatch.setattr(verification, "get_face_extractor", lambda settings: extractor)

    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()
    assert app.header[0].value == "Accueil"
    assert app.sidebar.radio[0].options == [
        "Accueil", "Personnes", "Vérifier un accès", "Compter les passages", "Historique",
    ]
    click(app, "Ouvrir le comptage")
    assert next(button for button in app.button if button.label == "Démarrer").disabled
    app.sidebar.radio[0].set_value("Historique").run()
    assert "Aucune tentative enregistrée" in app.info[0].value
    app.sidebar.radio[0].set_value("Accueil").run()
    click(app, "Ajouter une personne")
    assert app.header[0].value == "Personnes"
    app.text_input[0].set_value("Volontaire")
    click(app, "Créer la personne")
    user_id = next(iter(database.list_users(path)))
    assert app.selectbox[0].value == user_id
    assert app.dataframe[0].value["Statut"].tolist() == ["Visage à enregistrer"]

    app.sidebar.radio[0].set_value("Vérifier un accès").run()
    app.selectbox[0].set_value(user_id).run()
    assert "doit être enregistré" in app.info[0].value
    assert [button.label for button in app.button] == ["Enregistrer son visage"]
    click(app, "Enregistrer son visage")

    start_camera(app, released)
    click(app, "Arrêter la caméra")
    assert released.wait(2)
    app.run()
    assert any("Caméra arrêtée" in item.value for item in app.markdown)

    start_camera(app, released)
    app.sidebar.radio[0].set_value("Accueil").run()
    assert released.wait(2)
    app.sidebar.radio[0].set_value("Personnes").run()

    frame = capture(app, released)
    click(app, "Utiliser cette photo")
    np.testing.assert_array_equal(received[-1], frame.image)
    app.sidebar.radio[0].set_value("Accueil").run()
    app.sidebar.radio[0].set_value("Personnes").run()
    for _ in range(CAPTURES_REQUIRED - 1):
        capture(app, released)
        click(app, "Utiliser cette photo")
    click(app, "Enregistrer le visage")
    assert database.reference_count(path, user_id) == CAPTURES_REQUIRED
    assert "Visage enregistré" in app.success[0].value

    click(app, "Vérifier cette personne")
    assert app.selectbox[0].value == user_id
    capture(app, released)
    click(app, "Reprendre la photo")
    frame = capture(app, released)
    with database.connection(path) as db:
        assert db.execute("SELECT count(*) FROM verification_attempts").fetchone() == (0,)
    click(app, "Lancer la vérification")
    np.testing.assert_array_equal(received[-1], frame.image)
    assert len(opened) == CAPTURES_REQUIRED + 4
    assert app.success[0].proto.title == "Accès autorisé — simulation"
    app.run()
    click(app, "Voir l’historique")
    app.sidebar.radio[0].set_value("Vérifier un accès").run()
    with database.connection(path) as db:
        assert db.execute("SELECT count(*) FROM verification_attempts").fetchone() == (1,)

    click(app, "Voir l’historique")
    assert app.dataframe[0].value["Résultat"].tolist() == ["Autorisé"]

    app.sidebar.radio[0].set_value("Personnes").run()
    app.checkbox(key=f"delete_{user_id}").check().run()
    click(app, "Confirmer la suppression")
    assert not database.list_users(path)
    assert database.reference_count(path, user_id) is None
    assert not app.exception
