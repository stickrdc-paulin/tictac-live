# -*- coding: utf-8 -*-
"""
TICTAC Studio Regie — application Windows dédiée à la régie audio.

- Écran login uniquement (pas le site web)
- S’ouvre hors ligne sur le PC (UI locale) ; internet seulement pour login / sync
- Réutilise une session régie en cache ou une session WordPress admin navigateur
- Liste des reporteurs mise en cache à la connexion ou à la sync
- Statut « en ligne » seulement si le PC a internet ou LAN (+ app téléphone)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from app_update import check_for_update
from auth_session import APP_DIR, APP_VERSION
from local_server import start_server

TITLE = f"TICTAC Studio — Régie {APP_VERSION}"
EXE_NAME = "TICTAC-Studio-Regie.exe"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _self_path() -> Path:
    if _is_frozen():
        return Path(sys.executable).resolve()
    return Path(__file__).resolve()


def _kill_other_instances() -> None:
    """Ferme les anciennes instances TICTAC Studio (sauf le processus courant)."""
    if os.name != "nt":
        return
    me = os.getpid()
    self_name = _self_path().name.lower()
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"IMAGENAME eq {EXE_NAME}", "/FO", "CSV", "/NH"],
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return
    for line in out.splitlines():
        # "TICTAC-Studio-Regie.exe","1234","Session Name","1","12 345 K"
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) < 2:
            continue
        if parts[0].lower() != self_name and parts[0].lower() != EXE_NAME.lower():
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        if pid == me:
            continue
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                check=False,
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass


def _retire_old_copies(canonical: Path) -> None:
    """Supprime / remplace les anciennes copies hors dossier d’installation."""
    home = Path.home()
    candidates = [
        home / "Desktop" / EXE_NAME,
        home / "OneDrive" / "Desktop" / EXE_NAME,
        home / "Downloads" / EXE_NAME,
        home / "Téléchargements" / EXE_NAME,
        Path(r"E:\STICKHOSTING\tictac-live\windows-studio") / EXE_NAME,
        Path(r"E:\STICKHOSTING\tictac-live\downloads") / EXE_NAME,
    ]
    for path in candidates:
        try:
            if not path.is_file():
                continue
            if path.resolve() == canonical.resolve():
                continue
            # Ne pas effacer le binaire en cours d’exécution
            if _is_frozen() and path.resolve() == _self_path().resolve():
                continue
            path.unlink(missing_ok=True)
        except Exception:
            # Si verrouillé, tenter de remplacer au prochain lancement
            try:
                bak = path.with_suffix(".exe.old")
                path.replace(bak)
                bak.unlink(missing_ok=True)
            except Exception:
                pass


def ensure_installed() -> Path | None:
    """
    Installe / met à jour la copie canonique dans %LOCALAPPDATA%\\TICTAC-Studio
    et retire les anciennes EXE dispersées.

    Scénario MAJ depuis une ancienne install :
    - Setup Inno (même AppId) écrase {localappdata}\\TICTAC-Studio
    - Ou lancement d’un nouvel EXE portable → copie ici si version / taille différente
    """
    APP_DIR.mkdir(parents=True, exist_ok=True)
    canonical = APP_DIR / EXE_NAME
    version_file = APP_DIR / "version.txt"
    self_path = _self_path()

    if _is_frozen():
        need_copy = True
        if canonical.is_file():
            try:
                same = canonical.resolve() == self_path.resolve()
                current_ver = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else ""
                size_diff = canonical.stat().st_size != self_path.stat().st_size
                # Toujours propager si on lance un binaire hors dossier installé
                # avec une version différente (ex. Setup / EXE téléchargé versionné).
                need_copy = (not same) and (current_ver != APP_VERSION or size_diff)
                if same:
                    need_copy = False
                    if current_ver != APP_VERSION:
                        version_file.write_text(APP_VERSION, encoding="utf-8")
            except Exception:
                need_copy = True
        if need_copy and self_path.resolve() != canonical.resolve():
            try:
                shutil.copy2(self_path, canonical)
            except Exception:
                pass
        try:
            version_file.write_text(APP_VERSION, encoding="utf-8")
        except Exception:
            pass

    _retire_old_copies(canonical if canonical.is_file() else self_path)
    return canonical if canonical.is_file() else None


def _bg_check_update() -> None:
    try:
        check_for_update(open_browser=True)
    except Exception:
        pass


def main() -> int:
    _kill_other_instances()
    ensure_installed()
    threading.Thread(target=_bg_check_update, daemon=True).start()

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

    time.sleep(0.15)
    webview.start()
    _shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
