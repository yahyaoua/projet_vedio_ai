# SmartAccess React

Interface connectée à FastAPI pour l’enregistrement facial, la vérification d’accès et l’historique. Le comptage vidéo reste dans Streamlit.

## Démarrage local sous Windows

Utilisez Node.js 20.19 ou 22.12 et ultérieur, avec npm. Dans un premier PowerShell, depuis la racine de SmartAccess, lancez FastAPI avec la base existante.

```powershell
& .\.venv\Scripts\python.exe -m pip install -r .\requirements-api.txt
& .\.venv\Scripts\python.exe -m uvicorn src.smartaccess.api:app --host 127.0.0.1 --port 8000
```

Dans un second PowerShell, depuis la même racine.

```powershell
Set-Location .\frontend
node --version
npm.cmd --version
npm.cmd install
npm.cmd run typecheck
npm.cmd run build
npm.cmd run dev
```

Ouvrez [SmartAccess React](http://127.0.0.1:5173). Vite utilise le port 5173 et signale une erreur si ce port est occupé. La documentation FastAPI est disponible sur [le port 8000](http://127.0.0.1:8000/docs).

## Configuration des environnements

- Par défaut, le navigateur envoie ses requêtes à `/api` sur la même origine. Les serveurs de développement et de prévisualisation Vite relaient ce préfixe vers `http://127.0.0.1:8000`.
- Pour modifier la cible du proxy Vite, définissez par exemple `$env:SMARTACCESS_API_TARGET = 'http://127.0.0.1:9000'` avant de démarrer Vite. Redémarrez le serveur après modification.
- Pour servir `dist/` dans un autre environnement, configurez le serveur web pour relayer `/api` vers FastAPI sur la même origine que le frontend. Si le préfixe public diffère, définissez `VITE_API_BASE_URL` au moment du build, avec le préfixe complet, par exemple `/smartaccess/api`. Une URL vers une autre origine nécessite une configuration CORS explicite sur l’hôte qui répond à l’API.
- Le serveur FastAPI utilise la base existante définie par `SMARTACCESS_DB` et les modèles indiqués par `SMARTACCESS_MODELS`. Le parcours facial réutilise les tables existantes. Le seuil reste défini par `SMARTACCESS_VERIFICATION_THRESHOLD`.
- La webcam est ouverte par le navigateur après un clic. Utilisez la boucle locale ou HTTPS et arrêtez les acquisitions Streamlit avant d’utiliser la même caméra dans React.
- L’aperçu analyse jusqu’à trois images réduites par seconde. Pour ajuster la cadence, définissez par exemple `$env:VITE_FACE_PREVIEW_FPS = '2'` avant de démarrer Vite. Les valeurs sont limitées de 1 à 4.
- Les images JPEG ou PNG sont limitées à 2 Mio et 1920 pixels par côté. Les photos retenues pour l’enregistrement restent en mémoire dans le navigateur jusqu’à la validation, l’annulation ou la navigation. SQLite reçoit uniquement la référence calculée. L’historique conserve la décision et ses métadonnées.

## Vérification rapide

1. Dans le tableau de bord, comparez l’état du service avec `/api/health` et le nombre de comptes avec `/api/people`.
2. Dans **Personnes**, cherchez un nom puis un identifiant. Les homonymes doivent apparaître sur des lignes distinctes.
3. Dans **Historique**, choisissez un type et un résultat, puis appliquez les filtres. Téléchargez le CSV et vérifiez qu’il contient les lignes affichées, dans la limite sélectionnée. Les dates sont en UTC. Le CSV exclut les scores de similarité, les seuils, les images et les références biométriques.
4. Arrêtez votre instance de test FastAPI et actualisez le tableau de bord. Vérifiez le message d’erreur, puis relancez l’API et réessayez.

## Vérification de la caméra

1. Dans **Personnes**, créez ou sélectionnez un compte de test. Cliquez sur **Démarrer la caméra** et autorisez l’accès. Vérifiez que le cadre suit le visage et que les conseils changent avec le cadrage.
2. Cliquez sur **Capturer**, vérifiez la photo figée et essayez **Reprendre**. Retenez le nombre de photos demandé, puis enregistrez la référence. Pour un profil déjà enregistré, utilisez **Réenregistrer le visage**.
3. Cliquez sur **Vérifier un accès**, capturez une photo et lancez la comparaison. Consultez le résultat et les détails. Testez un titulaire, une autre personne et une photo sans visage.
4. Vérifiez dans **Historique** que chaque comparaison explicite ajoute une tentative, et que l’aperçu seul laisse le nombre de tentatives identique. Testez **Arrêter** et le changement de page pendant l’aperçu, puis vérifiez que la caméra peut être rouverte.
