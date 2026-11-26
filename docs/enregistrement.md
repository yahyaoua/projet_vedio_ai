# Acquisition et enregistrement facial

## Installation locale

Installe Python 3.12 x64 si nécessaire, puis ouvre la racine du projet dans le terminal PowerShell de VS Code. Crée l’environnement virtuel seulement lors de la première installation. Si le lanceur `py` est absent, utilise le chemin du Python 3.12 installé avec les mêmes arguments `-m venv .venv`.

```powershell
py -3.12 -m venv .venv
$smartAccessPython = ".\.venv\Scripts\python.exe"
& $smartAccessPython -m pip install -r .\requirements.txt
& $smartAccessPython -m pip check
& $smartAccessPython -m pytest -q
```

Place ces deux fichiers officiels dans `models/`. Sur GitHub, utilise le bouton de téléchargement du fichier. Les liens ci-dessous pointent aussi directement vers les fichiers binaires. SmartAccess vérifie leur empreinte SHA-256 au chargement.

- YuNet `face_detection_yunet_2023mar.onnx` pour OpenCV 4.x. [Fichier officiel OpenCV Zoo](https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx)
- SFace `face_recognition_sface_2021dec.onnx`. [Fichier officiel OpenCV Zoo](https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx)

```powershell
& $smartAccessPython -m src.smartaccess.media webcam --index 0
& $smartAccessPython -m streamlit run .\app.py --server.address 127.0.0.1
```

Le diagnostic webcam lit une image et affiche ses dimensions, puis libère la caméra, même en cas d’échec. Arrête la caméra dans SmartAccess avant de le lancer. Si nécessaire, essaie `--index 1`, `--backend dshow` ou `--backend msmf` et vérifie les permissions caméra de Windows.

Pour la vidéo de test, place un fichier MP4 H.264 dans `data/test.mp4`. Dans **Comptage**, sélectionne **Vidéo de test**, puis **Afficher la vidéo source** pour le lire dans le navigateur. Pour vérifier séparément le décodage OpenCV, lance la commande suivante. Elle lit les images une à une, puis ferme la vidéo.

```powershell
& $smartAccessPython -m src.smartaccess.media video
```

Les variables PowerShell suivantes permettent de modifier les valeurs par défaut avant de démarrer l’application. Les chemins relatifs partent de la racine du projet.

```powershell
$env:SMARTACCESS_DB = "data/smartaccess.sqlite3"
$env:SMARTACCESS_MODELS = "models"
$env:SMARTACCESS_VIDEO = "data/test.mp4"
$env:SMARTACCESS_MIN_FACE_PX = "100"
$env:SMARTACCESS_MIN_SHARPNESS = "80"
```

## Essai avec un volontaire

1. Dans **Personnes**, crée ou sélectionne un profil. Avec l’accord du volontaire, clique sur **Démarrer la caméra**. OpenCV ouvre la webcam du PC qui exécute Streamlit. Le réglage `SMARTACCESS_CAMERA_INDEX` sélectionne la webcam, avec `0` par défaut.
2. Vérifie que l’aperçu indique **Caméra active** et affiche les cadres YuNet. Essaie un cadre vide, deux visages, un visage éloigné et un mouvement rapide. La réponse dépend de la détection et des seuils configurés.
3. Quand l’aperçu indique que tu peux capturer, clique sur **Prendre une photo**. Examine l’image figée, puis clique sur **Utiliser cette photo** ou **Reprendre la photo**. Vérifie la progression et répète jusqu’au nombre de captures demandé.
4. Clique sur **Enregistrer le visage**, puis vérifie que la confirmation s’affiche. Tu peux quitter la page et revenir pour retrouver les captures déjà validées dans la même session.
5. Vérifie que l’indicateur de la webcam s’éteint après une capture, avec **Arrêter la caméra** et en quittant la page. Pour vérifier la suppression, utilise le profil créé pour cet essai et confirme sa suppression.

## Transformations et stockage

1. **Image.** OpenCV lit le flux dans un thread et un fragment Streamlit rafraîchit l’aperçu annoté. La capture fige l’image affichée. L’extracteur reçoit ses pixels au format PNG en mémoire, avec le cadre réservé à l’affichage.
2. **Visage détecté.** YuNet repère le rectangle du visage et des points comme les yeux et le nez. La capture est rejetée si YuNet détecte zéro visage ou plusieurs. Le rectangle visible doit atteindre la taille minimale sur chaque axe. Sur cette zone convertie en niveaux de gris, la variance du laplacien mesure la présence de variations nettes. Une valeur faible peut indiquer du flou. Le bruit, l’éclairage et le cadrage influencent ces mesures. Ces contrôles ne garantissent pas la qualité.
3. **Visage aligné.** SFace utilise les points du visage pour redresser et recadrer l’image dans un format commun.
4. **Embedding.** SFace transforme le visage aligné en un vecteur de 128 nombres. Le vecteur est ramené à une longueur de 1. Pendant l’enregistrement, les vecteurs des captures validées restent en mémoire.
5. **Référence stockée.** SmartAccess calcule la moyenne des trois vecteurs unitaires puis ramène cette moyenne à une longueur de 1. SQLite conserve ce vecteur au format binaire float32 little-endian, le modèle, la méthode, le nombre de captures et la date de mise à jour. La référence précédente est remplacée lors de la validation finale.

Les photos et les visages alignés sont traités en mémoire. L’application n’écrit aucun fichier image et ne stocke aucune photo en base. Les références numériques sont des données biométriques. Le dossier local `data/` est ignoré par Git. La suppression explicite d’un compte efface sa référence et retire le lien au compte des éventuelles tentatives historiques. Les événements de passage ne sont pas liés aux comptes.
