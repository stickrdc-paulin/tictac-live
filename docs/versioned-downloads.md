# Téléchargements versionnés et mises à jour

Complète la doc signature / version Setup (`studio-signing`) : noms de fichiers, `index.json`, MAJ depuis une ancienne install.

## Fichiers publiés (1.1.0)

| Artefact | Nom |
|----------|-----|
| APK Android | `TICTAC-LIVE-1.1.0.apk` |
| Setup Windows | `TICTAC-Studio-Regie-Setup-1.1.0.exe` |
| EXE portable (miroir) | `TICTAC-Studio-Regie.exe` |
| Catalogue | `downloads/index.json` |

Bump : éditer `android-shell/VERSION` et/ou `windows-studio/VERSION`, rebuild (`android-shell/build-release.ps1`, `windows-studio/build-release.bat`), republier les artefacts **et** `index.json` (GitHub + `wp-content/uploads/tictac-live/`).

## Windows — ancienne install → nouvelle

1. **Setup** : même `AppId` Inno + `UsePreviousAppDir=yes` + `CloseApplications=yes` → mise à jour de `%LOCALAPPDATA%\TICTAC-Studio` sans seconde entrée « Programmes ».
2. **EXE portable** : `ensure_installed()` copie vers le dossier canonique si version / taille différente.
3. **Check distant** : `app_update.py` lit `index.json` (site puis raw GitHub) ; si `windows_studio.version` > version locale, ouvre l’URL Setup versionnée.

## Android — ancienne install → nouvelle

1. Même `applicationId` (`cd.tictachebdo.live`).
2. `versionCode` dérivé du semver (1.1.0 → 10100) > ancien (1.0.0 → 1 ou 10000).
3. `UpdateChecker` ouvre l’URL APK versionnée si `index.json` annonce plus récent.

## WordPress

Plugin `stick-tth-live-apps.php` : constantes `STICK_TTH_LIVE_APPS_VERSION` + URLs `TICTAC-LIVE-<ver>.apk` / `TICTAC-Studio-Regie-Setup-<ver>.exe` (legacy non versionné en fallback).
