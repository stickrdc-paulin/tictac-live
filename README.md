# TICTAC LIVE

Applications terrain et régie pour [TIC-TAC Hebdo](https://tictachebdo.cd).

Compte GitHub : **stickrdc-paulin** (`stickrdc@gmail.com`)  
Dépôt : `https://github.com/stickrdc-paulin/tictac-live`  
Release : `https://github.com/stickrdc-paulin/tictac-live/releases/tag/v1.0.0`

## Applications

| App | Public | Dossier | Binaire |
|-----|--------|---------|---------|
| **TICTAC LIVE** | Reporters (Android) | `android-shell/` | `TICTAC-LIVE.apk` |
| **TICTAC Studio Regie** | Admin / régisseur (Windows) | `windows-studio/` | `TICTAC-Studio-Regie.exe` |

## Usage reporters

1. Compte contributeur sur tictachebdo.cd
2. Mon compte → **Télécharger TICTAC LIVE (Android)** ou **Envoyer au studio**
3. Activer le micro → la régie voit le reporter

## Usage régie (studio)

1. Compte administrateur
2. Mon compte → **Télécharger TICTAC Studio (Windows)**
3. Installer sur le PC studio → connexion à `/direct/studio`
4. Sélectionner jusqu’à 3 reporters en mix

## Build

### Android

Ouvrir `android-shell/` dans Android Studio → Build APK → renommer en `TICTAC-LIVE.apk`.

### Windows

```bat
cd windows-studio
Lancer-TICTAC-Studio.bat
```

Ou :

```bat
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --onefile --windowed --name TICTAC-Studio-Regie studio_regie.py
```

## Releases

Publier les binaires dans GitHub Releases (`latest`) :

- `TICTAC-LIVE.apk`
- `TICTAC-Studio-Regie.exe`

Les boutons du dashboard pointent vers ces URLs.

## Streaming public

Écoute : `https://video2.getstreamhosting.com/radio/8000/stream`  
Le mot de passe SOURCE Icecast n’est **jamais** dans les apps.
