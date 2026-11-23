# Coordonnées streaming TIC-TAC

## Écoute publique (site + app)

| | |
|---|---|
| HTTPS | `https://video2.getstreamhosting.com/radio/8000/stream` |
| HTTP | `http://video2.getstreamhosting.com:8000/stream` |
| Statut JSON | `http://video2.getstreamhosting.com:8000/status-json.xsl` |
| Station | RADIO KIVU1 (Cue Radio / Icecast) |

## Encodeur studio — secrets hors git

### Option A — TICTAC Studio Regie (Windows, V1)

Dans l’app : onglet **Diffusion**. Config locale dans `%LOCALAPPDATA%\TICTAC-Studio\stream_config.json` (password SOURCE inclus, jamais syncé vers tictachebdo.cd ni le dépôt). Prérequis : **ffmpeg** dans le PATH (ou chemin renseigné). Playlists / jingles : onglets dédiés (inspiration My Radiomatisme).

### Option B — BUTT / Mixxx

Fichier local : `E:\STICKHOSTING\.secrets\tictac-radio-stream.env`

| Paramètre | Valeur |
|---|---|
| Protocol | Icecast 2 |
| Server | `video2.getstreamhosting.com` |
| Port | `8000` |
| Mount | `/stream` |
| User | `source` |
| SSL | **OFF** (TLS uniquement pour l’écoute proxy 443) |

Le mot de passe SOURCE se régénère dans le panneau GetStreamHosting. Ne pas le mettre dans l’APK. Un seul encodeur à la fois sur le mount.

## Reporter terrain

1. Compte WordPress avec droit de contribution sur tictachebdo.cd
2. App TICTAC LIVE → onglet **Reporter** (ou `/direct/reporter.php`)
3. Régisseur / admin ouvre Studio Regie (ou `/direct/studio.php`) et sélectionne le micro
4. Playlists / jingles : Studio Regie pousse les fichiers vers Icecast via ffmpeg ; le mix reporters WebRTC reste écoute locale en V1
