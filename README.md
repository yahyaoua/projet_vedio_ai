# SmartAccess

Prototype local de vérification faciale 1:1 et de comptage de passages.

## Installer et contrôler les modèles sous Windows

Depuis la racine du projet dans PowerShell, utilise Python 3.12 x64. Crée `.venv` lors de la première installation. Si un environnement existe déjà, vérifie d’abord que son Python démarre.

```powershell
py -3.12 -m venv .venv
$smartAccessPython = ".\.venv\Scripts\python.exe"
& $smartAccessPython -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
& $smartAccessPython -m pip install -r .\requirements.txt
& $smartAccessPython -m src.smartaccess.model_setup --download
```

| Poids | Usage | Source officielle |
| --- | --- | --- |
| `models/face_detection_yunet_2023mar.onnx` | Détection du visage | [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) |
| `models/face_recognition_sface_2021dec.onnx` | Extraction de l’embedding facial | [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface) |
| `models/yolo11n.pt` | Détection des personnes pour le comptage | [Ultralytics v8.3.0](https://github.com/ultralytics/assets/releases/tag/v8.3.0) |

La commande télécharge uniquement les fichiers manquants. Elle rejette les pages HTML et les pointeurs Git LFS, vérifie le SHA-256 des fichiers OpenCV Zoo et contrôle la structure et l’intégrité de l’archive PyTorch de YOLO11n. Elle tente ensuite de charger chaque modèle avec OpenCV ou Ultralytics. Un fichier existant est vérifié sur place. S’il est invalide, déplace-le explicitement avant de relancer le téléchargement.

Pour vérifier les poids déjà installés sans téléchargement :

```powershell
& $smartAccessPython -m src.smartaccess.model_setup
```

`SMARTACCESS_MODELS` permet de choisir un autre dossier. Les chemins relatifs sont résolus depuis la racine de SmartAccess, quel que soit le dossier courant. `.gitignore` exclut le dossier `models/` et les extensions `.onnx` et `.pt`.

## Lancer l’application

```powershell
& .\.venv\Scripts\python.exe -m streamlit run .\app.py --server.address 127.0.0.1
```

Ouvre `http://127.0.0.1:8501`. Depuis un autre dossier, utilise les chemins absolus vers le Python de `.venv` et vers `app.py`.

[Validation locale](docs/validation.md) · [Enregistrement facial](docs/enregistrement.md) · [Comptage](docs/comptage.md)

## API locale

La première étape de migration ajoute une API FastAPI de lecture à côté de Streamlit. Les commandes Windows, les routes et le plan écran par écran figurent dans le [guide de migration React et FastAPI](docs/migration-react-fastapi.md).

L’[interface React locale](frontend/README.md) permet de consulter le tableau de bord, les comptes et l’historique à partir de cette API.
