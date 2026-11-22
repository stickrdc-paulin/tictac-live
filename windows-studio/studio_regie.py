# -*- coding: utf-8 -*-
"""
TICTAC Studio Regie — application Windows pour la régie.
Ouvre la régie TIC-TAC (/direct/studio) et liste les reporters connectés.
"""
from __future__ import annotations

import sys

STUDIO_URL = "https://tictachebdo.cd/direct/studio.php"
TITLE = "TICTAC Studio — Régie"

try:
    import webview
except ImportError:
    print("Installez pywebview : python -m pip install pywebview")
    sys.exit(1)


def main() -> int:
    webview.create_window(
        TITLE,
        STUDIO_URL,
        width=1280,
        height=860,
        min_size=(900, 600),
        confirm_close=True,
    )
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
