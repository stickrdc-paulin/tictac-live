# TICTAC LIVE

Application Android pour les reporters de [TIC-TAC Hebdo](https://tictachebdo.cd).

## À quoi ça sert

- **Écouter** la radio en ligne (flux Icecast public).
- **Émettre** depuis le terrain : connexion micro vers la régie (`/direct/reporter`), réservée aux comptes WordPress autorisés (contributeur / admin / régisseur).

Le mot de passe SOURCE Icecast **n’est jamais** dans l’app. Seule la régie (ou un encodeur studio) pousse vers l’antenne publique.

## Flux

1. Le reporter ouvre TICTAC LIVE et se connecte avec son compte TIC-TAC.
2. Il active le micro → la régie le voit dans `/direct/studio`.
3. Le régisseur / admin sélectionne le reporter (mix jusqu’à 3) et met à l’antenne.
4. Le public écoute sur le site (barre radio) ou dans l’onglet Écouter de l’app.

## Build APK (Android Studio)

1. Ouvrir le dossier `android-shell/` dans Android Studio.
2. Sync Gradle → Build → Build Bundle(s) / APK(s) → Build APK(s).
3. Installer sur le téléphone (sources inconnues si hors Play Store).

Package : `cd.tictachebdo.live`

## Serveur streaming (écoute publique)

- HTTPS : `https://video2.getstreamhosting.com/radio/8000/stream`
- Statut : via `admin-ajax.php?action=stick_tth_radio_status` sur le site

## Permissions

- Micro (émission reporter)
- Internet
- Audio (écoute en arrière-plan limitée au WebView)
