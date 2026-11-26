# Comptage sur vidéo locale

## Lancer le comptage

Depuis la racine du projet, utilise l’environnement Python 3.12 décrit dans le [guide d’enregistrement](enregistrement.md). La première commande installe les paquets CPU de PyTorch. Le comptage fonctionne sur CPU par défaut.

```powershell
$smartAccessPython = ".\.venv\Scripts\python.exe"
& $smartAccessPython -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
& $smartAccessPython -m pip install -r .\requirements.txt
& $smartAccessPython -m pip check
& $smartAccessPython -m pytest -q
```

Télécharge les poids depuis la publication officielle Ultralytics et la vidéo de démonstration depuis le tag OpenCV. Les commandes préservent les fichiers déjà présents. Si un téléchargement échoue, `curl` retire son fichier incomplet. [Poids YOLO11](https://github.com/ultralytics/assets/releases/tag/v8.3.0) · [Vidéo vtest.avi](https://github.com/opencv/opencv/blob/4.13.0/samples/data/vtest.avi)

```powershell
New-Item -ItemType Directory -Force -Path .\data, .\models | Out-Null
if (-not (Test-Path -LiteralPath .\models\yolo11n.pt)) {
    curl.exe --fail --location --remove-on-error --output .\models\yolo11n.pt https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt
}
if (-not (Test-Path -LiteralPath .\data\vtest.avi)) {
    curl.exe --fail --location --remove-on-error --output .\data\vtest.avi https://raw.githubusercontent.com/opencv/opencv/4.13.0/samples/data/vtest.avi
}
$env:SMARTACCESS_VIDEO = "data/vtest.avi"
Get-FileHash -Algorithm SHA256 .\data\vtest.avi, .\models\yolo11n.pt
& $smartAccessPython -m src.smartaccess.media video
& $smartAccessPython -m streamlit run .\app.py --server.address 127.0.0.1
```

Ouvre **Comptage**, règle la hauteur de ligne, la tolérance et le sens d’entrée, puis démarre une session. Pour répéter l’essai, garde le même fichier, les mêmes réglages et les mêmes versions de paquets. Cette vidéo permet de vérifier la lecture et le suivi. Pour vérifier les totaux, filme un court clip fixe où un volontaire traverse la ligne dans chaque sens et s’éloigne de la bande après chaque passage. Note à l’avance les passages attendus et utilise ce même fichier pour les essais suivants.

## Du suivi aux événements

Un modèle YOLO11n est chargé une fois par exécution. Le traitement transmet les images successives à ByteTrack via Ultralytics, avec le filtre COCO `classes=[0]` pour la classe personne. ByteTrack associe les boîtes entre images et leur attribue des identifiants temporaires. [Suivi Ultralytics](https://docs.ultralytics.com/modes/track) · [Filtre de classe](https://docs.ultralytics.com/tasks/detect)

Le point de référence est le milieu du bord inférieur de la boîte. Sa hauteur est exprimée en pourcentage de l’image. La ligne est horizontale, sur toute la largeur. Les deux traits fins délimitent la bande de tolérance. Pour chaque identifiant, le compteur compare la position actuelle au dernier côté observé hors de cette bande. Un déplacement dans la bande ne déclenche rien. Lorsque le point atteint le côté opposé hors de la bande, un passage est enregistré. Le nouveau côté devient le point de départ possible d’un retour. Un identifiant qui apparaît dans la bande doit d’abord atteindre un côté extérieur avant de pouvoir être compté.

SQLite conserve l’identifiant de la session, la date UTC de l’enregistrement, le sens et l’identifiant temporaire. Chaque démarrage repart de la première image avec une nouvelle session et un nouveau tracker. Les identifiants sont propres à la session et indépendants des comptes utilisateurs.

Si une personne est masquée ou que le tracker lui réattribue un identifiant, le compteur peut manquer un passage. Un échange d’identifiants entre deux personnes peut en créer un de trop. L’historique géométrique d’un identifiant expire lorsque sa dernière observation remonte à plus de 30 images. Une bande plus large atténue les oscillations mais exige que la personne s’éloigne davantage pour confirmer le passage.

## Interface, vitesse et arrêt

Une tâche de fond traite une seule vidéo à la fois. Un fragment Streamlit rafraîchit l’aperçu annoté et les compteurs environ quatre fois par seconde. Il affiche la dernière image traitée. Des images peuvent être sautées dans l’aperçu, mais le traitement lit chaque image de la vidéo dans l’ordre. La vitesse affichée est le nombre d’images traitées par seconde depuis le début de la lecture, décodage, suivi, annotation et écritures SQLite compris. Le chargement initial du modèle et le rendu dans le navigateur sont exclus.

**Arrêter le comptage** ou changer de page demande l’arrêt. La tâche termine le traitement déjà engagé, libère le lecteur OpenCV et conserve les événements déjà écrits. Le lecteur est également libéré en fin de fichier ou sur erreur. Si le navigateur est fermé directement, une vidéo peut se poursuivre jusqu’à la fin du fichier.

Après l’essai vidéo, sélectionne **Webcam** pour essayer la caméra locale. SmartAccess partage le même accès OpenCV entre les captures de visage et le comptage, avec une seule ouverture webcam à la fois dans le processus. Le réglage `SMARTACCESS_CAMERA_INDEX` vaut `0` par défaut. Le comptage webcam demande l’arrêt s’il ne reçoit plus de rafraîchissement de l’interface pendant 30 secondes et que la lecture d’image rend la main.

Le bilan d’une session correspond aux entrées moins les sorties observées pendant cette session. Il ne permet pas de connaître le nombre de personnes présentes.

Dans **Historique**, les filtres portent sur le type, le résultat, la session de comptage et les dates UTC. L’export CSV reprend les lignes affichées avec les mêmes filtres. Les données biométriques restent dans la table des références faciales.
