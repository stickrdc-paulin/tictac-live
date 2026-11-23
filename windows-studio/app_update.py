# -*- coding: utf-8 -*-
"""Vérification de mise à jour TICTAC Studio (index.json distant)."""
from __future__ import annotations

import json
import webbrowser
from typing import Any

import requests

from auth_session import APP_VERSION

INDEX_URLS = (
    # Catalogue seulement (JSON) — les binaires sont sur GitHub Releases, pas Verpex.
    "https://raw.githubusercontent.com/stickrdc-paulin/tictac-live/main/downloads/index.json",
    "https://tictachebdo.cd/wp-content/uploads/tictac-live/index.json",
)


def _parse_semver(value: str) -> tuple[int, int, int]:
    parts = (value or "").strip().split(".")
    nums: list[int] = []
    for i in range(3):
        try:
            nums.append(int(parts[i]) if i < len(parts) else 0)
        except ValueError:
            nums.append(0)
    return nums[0], nums[1], nums[2]


def is_newer(remote: str, local: str) -> bool:
    return _parse_semver(remote) > _parse_semver(local)


def fetch_windows_meta(timeout: float = 4.0) -> dict[str, Any] | None:
    for url in INDEX_URLS:
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code != 200:
                continue
            data = r.json()
            win = data.get("windows_studio") if isinstance(data, dict) else None
            if isinstance(win, dict) and win.get("version"):
                return win
        except (OSError, ValueError, json.JSONDecodeError, requests.RequestException):
            continue
    return None


def check_for_update(open_browser: bool = True) -> dict[str, Any] | None:
    """
    Si une version plus récente est publiée, ouvre l’URL du Setup versionné.
    Retourne le méta distant si MAJ dispo, sinon None.
    """
    meta = fetch_windows_meta()
    if not meta:
        return None
    remote_ver = str(meta.get("version") or "").strip()
    if not remote_ver or not is_newer(remote_ver, APP_VERSION):
        return None
    download = (
        str(meta.get("download") or "").strip()
        or str(meta.get("setup_github_release") or "").strip()
        or str(meta.get("github_release") or "").strip()
    )
    if open_browser and download:
        try:
            webbrowser.open(download)
        except Exception:
            pass
    return meta
