# Migration locale de SmartAccess

SmartAccess est un prototype de supervision vidéo et de contrôle d’accès sur un PC. L’avis public n° 09/2025 de la Préfecture de Rabat porte sur le contrôle d’accès par reconnaissance faciale et la vidéosurveillance intelligente. Le texte intégral du CPS reste à obtenir. La correspondance ci-dessous s’appuie sur l’objet de l’avis et sur le périmètre logiciel décrit pour le prototype. La validation article par article dépendra du CPS original. [Avis n° 09/2025 repris par MarocBiz](https://marocbiz.com/ao/mise-en-place-d-une-solution-de-controle-d-acces-par-reconnaissance-fa-g3h-914994)

## Services réutilisables

| Service | Responsabilité actuelle |
| --- | --- |
| [config.py](../src/smartaccess/config.py) et [model_setup.py](../src/smartaccess/model_setup.py) | Paramètres locaux et contrôle des fichiers de modèles. |
| [database.py](../src/smartaccess/database.py) | SQLite, profils, références faciales et persistance des événements. |
| [faces.py](../src/smartaccess/faces.py) | YuNet, contrôles de qualité, extraction SFace et construction de la référence. |
| [verification.py](../src/smartaccess/verification.py) | Vérification 1:1 du profil sélectionné, seuil de similarité et déduplication par identifiant de demande. |
| [media.py](../src/smartaccess/media.py) et [preview.py](../src/smartaccess/preview.py) | Acquisition OpenCV sur le PC qui exécute Python, verrou de caméra, aperçu facial et arrêt du traitement. |
| [counting.py](../src/smartaccess/counting.py) et [crossing.py](../src/smartaccess/crossing.py) | Détection et suivi des personnes, annotations, règles de franchissement et persistance des passages. |
| [history.py](../src/smartaccess/history.py) | Lecture SQLite filtrée et export CSV. La lecture structurée est partagée par l’API et le tableau Streamlit. |

## Couplages à extraire de Streamlit

- **Enregistrement.** `app.py` conserve la photo figée, les captures valides et leurs empreintes de déduplication dans `st.session_state`. Un service d’enregistrement devra gérer le brouillon par profil, valider une capture, annuler ou enregistrer l’ensemble. React conservera l’état des boutons et l’étape affichée.
- **Vérification.** L’interface conserve la photo et crée l’identifiant de demande au lancement. Le futur contrat doit rattacher la photo à une session et à un profil, puis accepter une soumission explicite et rejouable. `verification.verify` reste responsable de la décision et de l’écriture idempotente.
- **Vidéo.** Streamlit crée les traitements, envoie les signaux de présence et les arrête lors de la navigation. Ces responsabilités passeront à un gestionnaire de sessions côté serveur. Les fragments Streamlit restent une solution d’affichage propre à l’interface actuelle.
- **Historique et état.** Les codes métier restent communs. React traduira les libellés et formatera les dates. L’export devra réutiliser les mêmes filtres SQLite, sans dépendre de la limite d’affichage du tableau. L’état du service, la présence des poids, leur chargement et l’état réel de la caméra doivent rester distincts.

## Correspondance avec le périmètre logiciel

**Observé** désigne un comportement vu sur une interface lancée. **Testé automatiquement** inclut les tests à captures ou trajectoires simulées. **Restant à tester** décrit les contrôles matériels et métier qui demandent un essai local.

| Volet | Observé | Testé automatiquement | Restant à tester | Simulé ou hors périmètre |
| --- | --- | --- | --- | --- |
| Gestion des personnes | Page et état vide Streamlit | Création, référence, reprise du parcours et suppression | Enregistrement avec de vraies captures | Administration à grande échelle hors périmètre |
| Contrôle d’accès facial | Parcours visible dans Streamlit | Vérification 1:1, seuil, captures invalides, persistance et déduplication | Essais avec deux volontaires et les poids installés, sous plusieurs éclairages | Ouverture simulée. Portes et barrières physiques hors périmètre |
| Visualisation et analyse vidéo | État « Caméra arrêtée » observé dans Streamlit | Aperçu facial avec images simulées, choix de l’image utilisée et libération du flux | Fluidité et reprise avec la webcam, chargement de YuNet/SFace et suivi YOLO sur vidéo réelle | Parc massif de caméras hors périmètre |
| Comptage des passages | Page de comptage et blocage sans vidéo locale observés | Franchissements, sens, compteurs et persistance sur trajectoires simulées | Entrée, sortie, stationnement près de la ligne et réouverture de la caméra après arrêt | Mesure d’occupation d’un bâtiment hors périmètre |
| Historique et exports | Page et état vide Streamlit | Filtres, CSV et absence de référence biométrique dans l’export | Recette avec des événements issus des essais matériels | Rapports d’exploitation du marché hors périmètre |
| Infrastructure | Exécution locale | — | — | Redondance, cluster, bascule, infrastructure de site et recette du marché hors périmètre |

Les procédures d’essai du matériel sont regroupées dans le [guide de validation](validation.md).

## API de la première étape

| Route | Réponse |
| --- | --- |
| `GET /api/health` | État du service et accès aux tables de lecture. HTTP 503 si SQLite est indisponible ou si le schéma requis manque. |
| `GET /api/people` | Liste des profils, avec `id` et `name`. |
| `GET /api/history` | Événements du plus récent au plus ancien, avec codes stables et dates ISO en UTC. |

Les filtres combinables sont `kind` (`verification` ou `passage`), `outcome` (`authorized`, `denied`, `invalid_capture`, `entry` ou `exit`), `session`, `start`, `end` et `limit`. Les dates inclusives suivent le format `AAAA-MM-JJ` en UTC. La limite vaut 100 par défaut et accepte de 1 à 500 lignes. Des filtres valides sans correspondance renvoient une liste vide. Un paramètre invalide ou une plage de dates inversée renvoie HTTP 422.

Les routes ouvrent la base configurée par `SMARTACCESS_DB` en lecture seule. Le chemin par défaut est `data/smartaccess.sqlite3`. Pour une nouvelle base ou un ancien schéma, lancez d’abord Streamlit, qui utilise l’initialisation et les migrations SQLite existantes. Les réponses exposent uniquement les champs déclarés. La similarité et le seuil sont des métadonnées de tentative. Les images, embeddings, références et identifiants de demande restent côté serveur.

### Commandes Windows

Depuis la racine du projet, dans PowerShell, avec le Python 3.12 de l’environnement Streamlit déjà installé.

```powershell
$smartAccessPython = '.\.venv\Scripts\python.exe'
& $smartAccessPython -m pip install -r .\requirements-api.txt
& $smartAccessPython -m pytest -q -rs
& $smartAccessPython -m uvicorn src.smartaccess.api:app --host 127.0.0.1 --port 8000
```

Dans un second PowerShell.

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/health'
Invoke-RestMethod 'http://127.0.0.1:8000/api/people'
Invoke-RestMethod 'http://127.0.0.1:8000/api/history?kind=verification&limit=10'
Invoke-RestMethod 'http://127.0.0.1:8000/api/history?kind=passage&outcome=entry&limit=10'
```

La documentation interactive est disponible dans [Swagger UI](http://127.0.0.1:8000/docs). Pour contrôler Streamlit dans un autre terminal, lancez `& .\.venv\Scripts\python.exe -m streamlit run .\app.py --server.address 127.0.0.1`.

## Plan écran par écran

| Écran React | Première livraison | Suite |
| --- | --- | --- |
| Tableau de bord | État de l’API et de SQLite, raccourcis et derniers événements réels | Ajouter des états distincts pour la présence des poids, le chargement et l’acquisition vidéo |
| Personnes | Liste et état vide à partir de `/api/people` | Ajouter création, suppression confirmée et enregistrement progressif. Exposer seulement un indicateur de référence disponible |
| Contrôle d’accès | Préparer la sélection du profil et les états du parcours | Raccorder la capture figée et la vérification explicite. Afficher la décision, les détails et le libellé d’ouverture simulée |
| Supervision vidéo | Définir les commandes et les états de la session | Après validation du cycle de vie, raccorder la webcam ou le fichier vidéo, les annotations et les compteurs |
| Événements et rapports | Brancher les filtres, l’affichage UTC et les états vides sur `/api/history` | Ajouter une route CSV à partir des mêmes filtres, avec un contrat explicite pour la pagination et l’export |
| À propos du projet | Présenter l’objectif, la référence au marché et les limites du prototype | Tenir à jour les résultats des essais et le périmètre à partir du CPS original |

Migrer d’abord les écrans de lecture et conserver Streamlit pendant la recette. L’interface React pourra accéder à `/api` par un proxy de développement de même origine. Les mutations et le média viendront après les contrats de session et leurs tests.

## Acquisition vidéo future

| Option | Conséquence |
| --- | --- |
| OpenCV côté FastAPI | Le serveur local ouvre la webcam ou la vidéo et réutilise la chaîne d’analyse existante. |
| Webcam côté navigateur | Le navigateur gère les permissions et doit transmettre les images au serveur pour l’analyse. Convient surtout si le navigateur et Python tournent sur des machines différentes. |
| Source réseau IP | Le serveur se connecte à une caméra distante et gère les identifiants et reconnexions de la source. |

Pour ce prototype sur un seul PC, retenir **OpenCV côté FastAPI**, avec un seul processus responsable de la caméra. Le verrou actuel est interne à un processus. Pendant la coexistence, arrêter l’acquisition Streamlit avant de démarrer l’acquisition FastAPI sur le même périphérique.

Avant d’ajouter un flux, définir l’ouverture explicite et le propriétaire de la session, le passage à l’état actif à la première image, l’arrêt idempotent, le refus d’une deuxième ouverture, et la libération à la déconnexion, à l’expiration, sur erreur et à l’arrêt serveur. Définir aussi le rattachement de la photo figée à la session et au profil, le nombre d’images conservées en mémoire et la durée de vie de la photo. La première étape couvre uniquement la lecture HTTP de l’état, des profils et des événements.
