# Validation de SmartAccess sur Windows

## Démarrage et résultats

Depuis PowerShell, utilise Python 3.12 x64 et l’environnement virtuel du projet. Pour une première installation, suis les guides [enregistrement](enregistrement.md) et [comptage](comptage.md) pour les dépendances et les poids officiels. Utilise un fichier SQLite dédié pour l’essai. Garde le même chemin au redémarrage pour contrôler la persistance.

```powershell
Set-Location -LiteralPath 'C:\Users\Victus\Desktop\projet_sebbar'
$env:SMARTACCESS_DB = 'data/validation.sqlite3'
$env:SMARTACCESS_VIDEO = 'data/passages-validation.mp4'
$env:SMARTACCESS_CAMERA_INDEX = '0'
$env:SMARTACCESS_VERIFICATION_THRESHOLD = '0.363'
& .\.venv\Scripts\python.exe -m pytest -ra
& .\.venv\Scripts\python.exe -m streamlit run .\app.py --server.address 127.0.0.1
```

Ouvre `http://127.0.0.1:8501`. Pour lancer uniquement l’application avec la configuration déjà en vigueur, utilise la dernière commande.

## Tests automatisés

| Groupe | Action du test | Résultat attendu |
| --- | --- | --- |
| Décision | Comparer des scores juste sous le seuil, au seuil et juste au-dessus. | Refus sous le seuil, autorisation à partir du seuil inclus. |
| Capture invalide | Soumettre des cas sans visage, avec plusieurs visages, avec un visage trop petit ou flou. Rejouer une capture invalide, puis soumettre une nouvelle capture avec un autre identifiant. | Les captures invalides sont rejetées. Une tentative invalide conserve un score vide. Son rejeu garde une seule ligne et la nouvelle capture obtient sa propre tentative. |
| Doublons | Rejouer une soumission, envoyer deux écritures concurrentes pour le même identifiant et relancer l’interface après une vérification. | Le premier résultat est conservé, les deux écritures lisent le même résultat et la base contient une ligne pour cet identifiant. |
| Franchissements | Injecter des trajectoires d’entrée, de sortie, de stationnement, d’oscillation et d’aller-retour. Inverser le sens d’entrée et répéter sur deux sessions. | Une entrée et une sortie dans le sens configuré, aucun passage en restant dans la bande, deux passages pour un aller-retour complet. Chaque session a son propre identifiant. |
| SQLite et CSV | Réinitialiser un schéma existant, supprimer un compte, filtrer l’historique par type, résultat, session et date, puis lire le CSV produit. | Les lignes antérieures sont conservées, la référence du compte supprimé disparaît, les tentatives sont conservées sans lien au compte, et les lignes exportées correspondent au filtre sans données de référence. |

Les tests utilisant des captures, embeddings ou pistes synthétiques couvrent les règles de l’application. La reconnaissance et le suivi avec les vrais poids se vérifient avec le protocole ci-dessous.

## Tests manuels avec deux volontaires

Pour chaque ligne, relève la date, le résultat observé et le statut **réussi**, **échec** ou **non exécuté**. Pour les essais faciaux, note le code A ou B, l’éclairage, l’issue et la similarité affichée lorsqu’elle existe. Utilise trois séries de photos distinctes pour l’enregistrement, l’éventuel réglage et l’essai final. Si tu changes le seuil, redémarre l’application, fige-le avant l’essai final et utilise de nouvelles captures. Le [protocole de vérification](verification.md) détaille cette séparation.

| Test | Actions | Résultat attendu |
| --- | --- | --- |
| Caméra intégrée | Ferme les autres applications caméra et débranche les webcams externes. Exécute `& .\.venv\Scripts\python.exe -m src.smartaccess.media webcam --index 0` dans un second terminal PowerShell. | OpenCV lit une image et affiche ses dimensions. L’indicateur de la webcam s’éteint après la commande, si le matériel en possède un. |
| Compte sans référence | Crée deux comptes de test A et B, avec l’accord des collègues. Sélectionne A dans **Vérification d’accès** avant de l’enregistrer. | L’application demande une référence. Aucune tentative et aucune capture ne sont déclenchées. |
| Enregistrement | Dans **Utilisateurs**, sélectionne A. Prends trois photos valides de A, enregistre la référence et recharge l’application. | Le compteur passe à trois et la référence est encore affichée après rechargement. |
| Titulaire et autre volontaire | Dans **Vérification d’accès**, sélectionne le compte A. Vérifie A, puis B sur le même compte, en lumière diffuse puis en lumière faible ou en contre-jour. Utilise une nouvelle capture à chaque essai. | Pour un score valide, le résultat suit la règle du seuil. L’objectif est d’autoriser A et de refuser B. Tout écart ou capture invalide est consigné avec l’éclairage et le score disponible. |
| Capture invalide et nouvelle tentative | Soumets une image sans personne, puis une avec A et B clairement visibles. Vérifie dans **Historique**, puis reviens faire une nouvelle capture avec A seul. | Les deux premiers essais sont invalides si YuNet détecte respectivement zéro et deux visages. Chaque tentative invalide demande une nouvelle photo et a un score vide. Une nouvelle capture déclenche une nouvelle tentative. |
| Reruns et doublons | Note le nombre de lignes après une vérification. Change de page, recharge l’onglet puis reviens dans **Historique**, sans cliquer de nouveau sur le bouton de capture. | Le nombre de tentatives reste identique. |
| Vidéo et deux sens | Enregistre un MP4 avec un plan fixe. Fais déplacer A du haut vers le bas, le faire rester du même côté en s’approchant de la ligne, puis revenir du bas vers le haut. Garde ses pieds visibles. Note les deux passages attendus avant l’analyse. Place le MP4 dans `data/passages-validation.mp4`, règle la ligne et la bande sur la vidéo, puis lance **Comptage**. | Une entrée, une sortie et aucun passage supplémentaire pendant le stationnement. L’aperçu montre le suivi, la ligne et un débit mesuré. Un second démarrage crée une autre session. Note tout changement d’identifiant ou écart. |
| Webcam et arrêt | Dans **Comptage**, choisis **Webcam**, puis arrête la session. Une fois l’arrêt affiché, relance le diagnostic webcam ou prends une photo de vérification. | L’image s’affiche si la caméra est disponible. La caméra est réutilisable après l’arrêt. |
| Persistance et CSV | Arrête Streamlit avec Ctrl+C et relance-le avec le même fichier SQLite. Dans **Historique**, filtre la session vidéo, le résultat **Entrée** et la date UTC de l’essai. Télécharge le CSV et compare-le au tableau. | Les événements persistent. Le CSV contient les mêmes lignes filtrées et aucune image, référence faciale ou embedding. |
