# -*- coding: utf-8 -*-
"""
TICTAC Studio Regie — application Windows dédiée à la régie audio.

- Écran login uniquement (pas le site web)
- Réutilise une session WordPress déjà ouverte dans Chrome/Edge/Firefox si admin
- Sinon demande une nouvelle connexion
- Affiche uniquement les reporters connectés et l’écoute studio (WebRTC)
"""
from __future__ import annotations

import sys
import threading
import time

from local_server import start_server

TITLE = "TICTAC Studio — Régie"


def main() -> int:
    try:
        import webview
    except ImportError:
        print("Installez pywebview : python -m pip install pywebview")
        return 1

    httpd, port = start_server(0)
    url = f"http://127.0.0.1:{port}/"

    window = webview.create_window(
        TITLE,
        url,
        width=980,
        height=820,
        min_size=(720, 560),
        confirm_close=True,
        background_color="#14110E",
    )

    def _shutdown() -> None:
        try:
            httpd.shutdown()
        except Exception:
            pass

    def _on_closed() -> None:
        threading.Thread(target=_shutdown, daemon=True).start()

    try:
        window.events.closed += _on_closed
    except Exception:
        pass

    # Laisser le serveur répondre avant le premier chargement.
    time.sleep(0.15)
    webview.start()
    _shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
