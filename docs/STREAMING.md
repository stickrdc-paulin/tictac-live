# Coordonnées streaming TIC-TAC

## Écoute publique (site + app)

| | |
|---|---|
| HTTPS | `https://video2.getstreamhosting.com/radio/8000/stream` |
| HTTP | `http://video2.getstreamhosting.com:8000/stream` |
| Statut JSON | `http://video2.getstreamhosting.com:8000/status-json.xsl` |
| Station | RADIO KIVU1 (Cue Radio / Icecast) |

## Encodeur studio (BUTT / Mixxx) — secrets hors git

Fichier local : `E:\STICKHOSTING\.secrets\tictac-radio-stream.env`

| Paramètre | Valeur |
|---|---|
| Protocol | Icecast 2 |
| Server | `video2.getstreamhosting.com` |
| Port | `8000` |
| Mount | `/stream` |
| User | `source` |
| SSL | **OFF** (TLS uniquement pour l’écoute proxy 443) |

Le mot de passe SOURCE se régénère dans le panneau GetStreamHosting. Ne pas le mettre dans l’APK.

## Reporter terrain

1. Compte WordPress avec droit de contribution sur tictachebdo.cd
2. App TICTAC LIVE → onglet **Reporter** (ou `/direct/reporter.php`)
3. Régisseur / admin ouvre `/direct/studio.php` et sélectionne le micro
4. La régie (PC studio) pousse le mix vers Icecast
