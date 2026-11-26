# Vérification faciale 1:1

## Démarrage local

Prépare Python, l’environnement virtuel et les modèles selon le [guide d’enregistrement](enregistrement.md). Dans PowerShell, à la racine du projet, lance les tests puis Streamlit.

```powershell
$smartAccessPython = ".\.venv\Scripts\python.exe"
$env:SMARTACCESS_VERIFICATION_THRESHOLD = "0.363"
& $smartAccessPython -m pytest -q
& $smartAccessPython -m streamlit run .\app.py --server.address 127.0.0.1
```

Dans **Vérifier un accès**, sélectionne un profil avec un visage enregistré et clique sur **Démarrer la caméra**. Lorsque YuNet indique que l’image est exploitable, clique sur **Prendre une photo**. La caméra locale est libérée après la prise. Examine la photo, puis clique sur **Lancer la vérification** ou **Reprendre la photo**. Seul le lancement de la comparaison peut créer une tentative dans l’historique. Si la comparaison rejette la photo, reprends-la. La tentative correspondante apparaît dans l’historique sans score.

## Règle de décision

Le seuil initial est **0,363**, valeur de similarité cosinus publiée pour SFace sur le jeu LFW. Elle sert de point de départ. SmartAccess compare la capture à la moyenne normalisée de trois embeddings et doit être évalué sur le matériel et les conditions du prototype. [Tutoriel OpenCV et tableau des seuils](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html)

La similarité cosinus est comprise entre −1 et 1. Un score plus élevé indique des vecteurs plus proches. Ce score ne représente pas une probabilité. La décision utilise la valeur calculée avant arrondi à l’affichage. Un score supérieur ou égal au seuil donne **autorisé**. Un score inférieur donne **refusé**. Pour changer le seuil, renseigne `SMARTACCESS_VERIFICATION_THRESHOLD` avec un point décimal, puis redémarre Streamlit.

Le service lit uniquement la référence du compte sélectionné. Il réutilise les contrôles d’enregistrement et extrait l’embedding de la photo en mémoire. SQLite conserve le compte, la date UTC, l’issue, le seuil et la similarité lorsqu’elle existe. Un identifiant unique par soumission protège l’historique contre les répétitions. La photo et l’embedding de vérification ne sont pas conservés. L’historique antérieur est conservé lors de la mise à jour du schéma. Si un compte est supprimé, les tentatives historiques sont conservées sans lien au compte.

L’ouverture de porte est simulée. Une photo ou une vidéo présentée à la caméra peut tromper ce prototype.

## Protocole local avec deux volontaires

1. Avec leur accord, désigne les volontaires A et B. Enregistre le compte A avec trois captures dédiées. Garde cette référence fixe pendant les deux séries suivantes.
2. **Réglage du seuil.** Teste le compte A avec A, puis avec B. Pour chaque personne, prends par exemple trois nouvelles photos en lumière diffuse de face, trois en lumière faible et trois en contre-jour. Garde autant que possible la même distance et la même pose. Relève le code du volontaire, l’éclairage, l’issue et la similarité affichée. Prends chaque photo au moment de l’essai, sans réutiliser les captures d’enregistrement.
3. Compare les scores valides des deux volontaires. Choisis et consigne un seuil à partir de cette série uniquement. Si les scores se chevauchent, note le compromis entre refus du bon volontaire et acceptation de l’autre. Relève les captures invalides à part, car elles ne produisent pas de similarité. Fige le seuil et les paramètres de capture avant de poursuivre.
4. **Test final.** Reprends le même plan avec de nouvelles photos distinctes de celles de l’enregistrement et du réglage. Applique le seuil figé pendant toute cette série. Pour chaque éclairage, relève le nombre d’acceptations et de refus pour A et B, ainsi que le nombre de captures invalides. Si tu modifies le seuil après avoir vu ces résultats, collecte une nouvelle série indépendante pour le prochain test final.
5. Avec un compte de test, essaie une capture sans visage, puis ouvre **Historique** sans soumettre de nouvelle photo. Vérifie que la capture invalide demande une nouvelle photo et que la navigation n’ajoute aucune tentative.

Pour consulter les dernières tentatives dans la base configurée, ouvre un second terminal PowerShell à la racine du projet. Utilise le même `SMARTACCESS_DB` si tu l’as personnalisé.

```powershell
$smartAccessPython = ".\.venv\Scripts\python.exe"
@'
from src.smartaccess.config import Settings
from src.smartaccess.database import connection

with connection(Settings().database) as db:
    rows = db.execute("""
        SELECT id, occurred_at, outcome, similarity, threshold
        FROM verification_attempts ORDER BY id DESC LIMIT 20
    """)
    for row in rows:
        print(row)
'@ | & $smartAccessPython -
```
