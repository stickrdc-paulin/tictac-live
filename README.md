# TICTAC LIVE

Applications terrain et régie pour [TIC-TAC Hebdo](https://tictachebdo.cd).

Compte GitHub : **stickrdc-paulin** (`stickrdc@gmail.com`)  
Dépôt : `https://github.com/stickrdc-paulin/tictac-live`  
Catalogue : [`downloads/index.json`](downloads/index.json)

## Applications

| App | Public | Dossier | Fichier téléchargé (versionné) |
|-----|--------|---------|--------------------------------|
| **TICTAC LIVE** | Reporters (Android) | `android-shell/` | `TICTAC-LIVE-1.1.0.apk` |
| **TICTAC Studio Regie** | Admin / régisseur (Windows) | `windows-studio/` | `TICTAC-Studio-Regie-Setup-1.1.0.exe` |

Versions sources : `android-shell/VERSION` et `windows-studio/VERSION` (actuellement **1.1.0**).

## Usage reporters

1. Compte contributeur sur tictachebdo.cd
2. Mon compte → **Télécharger TICTAC LIVE (Android)** ou **Envoyer au studio**
3. Activer le micro → la régie voit le reporter
4. MAJ : installer le nouvel APK **par-dessus** (même `applicationId`, `versionCode` plus élevé) — pas besoin de désinstaller

## Usage régie (studio)

1. Compte administrateur
2. Mon compte → **Télécharger TICTAC Studio (Windows)** → Setup versionné
3. Installer sur le PC studio (même AppId Inno → met à jour `%LOCALAPPDATA%\TICTAC-Studio`)
4. Sélectionner jusqu’à 3 reporters en mix
5. Au lancement, l’app consulte `index.json` et ouvre le Setup distant si une version plus récente est publiée

## Build

### Android

```powershell
cd android-shell
.\build-release.ps1
```

Sortie : `downloads/TICTAC-LIVE-<version>.apk` + mise à jour de `downloads/index.json`.

Ou Android Studio → Assemble Release (nom `TICTAC-LIVE-<versionName>` via `archivesBaseName`).

### Windows

Lancer / rebuild rapide :

```bat
cd windows-studio
Lancer-TICTAC-Studio.bat
```

Release (exe + installateur Inno Setup, version depuis `windows-studio/VERSION`, signature Authenticode optionnelle) :

```bat
cd windows-studio
build-release.bat
```

Sorties : `dist\TICTAC-Studio-Regie.exe` et `dist\installer\TICTAC-Studio-Regie-Setup-<version>.exe`, miroir dans `downloads/`.  
Signature : variables `TICTAC_CODE_SIGN_*` (voir `windows-studio/.env.example`). Aucun certificat dans le dépôt.

## Releases

Publier les binaires dans GitHub Releases (`latest`) **avec le numéro de version dans le nom** :

- `TICTAC-LIVE-1.1.0.apk`
- `TICTAC-Studio-Regie-Setup-1.1.0.exe` (installateur recommandé)
- `TICTAC-Studio-Regie.exe` (portable, optionnel)

Mettre aussi à jour `downloads/index.json` et le miroir `wp-content/uploads/tictac-live/` (y compris `index.json` pour les checks MAJ).

Les boutons WordPress (`stick-tth-live-apps.php`) pointent vers ces URLs versionnées.

## Streaming public

Écoute : `https://video2.getstreamhosting.com/radio/8000/stream`  

Encodeur : onglet **Diffusion** de TICTAC Studio Regie (config locale `%LOCALAPPDATA%\TICTAC-Studio\stream_config.json`, ffmpeg requis) ou BUTT/Mixxx. Le mot de passe SOURCE Icecast n’est **jamais** dans le dépôt ni l’APK (uniquement config locale régie si renseigné).
