# Téléchargements versionnés et mises à jour

## Principe : une Release GitHub suffit

Publier une **GitHub Release** (tag `vX.Y.Z` + assets) met à jour en même temps :

1. **Mon compte** (WordPress) — liens + libellés de version via l'API Releases (cache 6 h)
2. **TICTAC Studio (Windows)** — check in-app `GET /update` → GitHub Releases
3. **Secours** — `downloads/index.json` (raw GitHub) si l'API est indisponible

**Pas** de re-upload Verpex des EXE/APK.  
**Pas** d'édition manuelle du plugin WP à chaque bump.

## Assets à joindre à chaque Release

| Rôle | Nom (obligatoire) | Optionnel versionné |
|------|-------------------|---------------------|
| APK stable (site + `latest/download`) | `TICTAC-LIVE.apk` | `TICTAC-LIVE-X.Y.Z.apk` |
| EXE stable Windows | `TICTAC-Studio-Regie.exe` | `TICTAC-Studio-Regie-X.Y.Z.exe` |
| Setup Inno (si build) | — | `TICTAC-Studio-Regie-Setup-X.Y.Z.exe` |

Les URLs stables `releases/latest/download/TICTAC-LIVE.apk` et `…/TICTAC-Studio-Regie.exe` ne changent **jamais** de chemin : seul le fichier derrière `latest` change.

## Flux de publication

1. Bump `windows-studio` / `android-shell` VERSION, rebuild.
2. Créer la Release GitHub `vX.Y.Z` avec les assets (stables **et** versionnés).
3. Mettre à jour `downloads/index.json` sur `main` (version + URLs) — secours catalogue.
4. Rien à faire sur Verpex ni dans le mu-plugin (sauf premier déploiement du plugin dynamique).

## Windows — check in-app

- `windows-studio/app_update.py` interroge `api.github.com/.../releases/latest`.
- Compare `tag_name` (sans `v`) à `APP_VERSION` locale.
- UI : bandeau « Mise à jour disponible » + lien téléchargement (`/update`).
- Hors ligne / erreur réseau → `available=false`, `offline=true` — **aucun** faux positif bloquant.
- Ne force plus l'ouverture du navigateur au démarrage.

## WordPress (Mon compte)

Plugin `stick-tth-live-apps.php` (mu-plugin sur tictachebdo.cd) :

- Catalogue : GitHub API → index.json → noms stables `latest/download`
- Libellés : version lue dynamiquement (plus de constante produit hardcodée)
- Transient `stick_tth_live_apps_catalog` (6 h)

## Android

`UpdateChecker` peut continuer à lire `index.json` ; les tuiles Mon compte pointent déjà GitHub `latest`.
