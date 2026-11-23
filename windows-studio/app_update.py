# -*- coding: utf-8 -*-
"""Vérification de mise à jour TICTAC Studio via GitHub Releases."""
from __future__ import annotations

import json
import re
import threading
import webbrowser
from typing import Any

import requests

from auth_session import APP_VERSION

GITHUB_API_LATEST = (
    "https://api.github.com/repos/stickrdc-paulin/tictac-live/releases/latest"
)
GITHUB_HTML_LATEST = "https://github.com/stickrdc-paulin/tictac-live/releases/latest"
# Noms stables republés à chaque Release (ne changent pas avec le numéro de version).
STABLE_EXE_NAMES = (
    "TICTAC-Studio-Regie.exe",
    "TICTAC-Studio-Regie-Setup.exe",
)
INDEX_URLS = (
    "https://raw.githubusercontent.com/stickrdc-paulin/tictac-live/main/downloads/index.json",
    "https://tictachebdo.cd/wp-content/uploads/tictac-live/index.json",
)

_UA = "TICTAC-Studio-Regie/" + APP_VERSION
_cache_lock = threading.Lock()
_cache: dict[str, Any] | None = None


def _parse_semver(value: str) -> tuple[int, int, int]:
    cleaned = (value or "").strip().lstrip("vV")
    cleaned = re.split(r"[^0-9.]", cleaned, maxsplit=1)[0]
    parts = cleaned.split(".") if cleaned else []
    nums: list[int] = []
    for i in range(3):
        try:
            nums.append(int(parts[i]) if i < len(parts) else 0)
        except ValueError:
            nums.append(0)
    return nums[0], nums[1], nums[2]


def is_newer(remote: str, local: str) -> bool:
    return _parse_semver(remote) > _parse_semver(local)


def _pick_windows_asset(assets: list[dict[str, Any]], tag: str) -> tuple[str, str]:
    """Retourne (filename, browser_download_url) pour Windows."""
    by_name = {
        str(a.get("name") or ""): str(a.get("browser_download_url") or "")
        for a in assets
        if isinstance(a, dict)
    }
    ver = tag.lstrip("vV")
    preferred = [
        f"TICTAC-Studio-Regie-Setup-{ver}.exe",
        f"TICTAC-Studio-Regie-{ver}.exe",
        *STABLE_EXE_NAMES,
    ]
    for name in preferred:
        url = by_name.get(name) or ""
        if url:
            return name, url
    for name, url in by_name.items():
        if name.lower().endswith(".exe") and url:
            return name, url
    latest_stable = (
        "https://github.com/stickrdc-paulin/tictac-live/releases/latest/download/"
        + STABLE_EXE_NAMES[0]
    )
    return STABLE_EXE_NAMES[0], latest_stable


def _from_github_api(timeout: float) -> dict[str, Any] | None:
    try:
        r = requests.get(
            GITHUB_API_LATEST,
            timeout=timeout,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": _UA,
            },
        )
        if r.status_code != 200:
            return None
        data = r.json()
        if not isinstance(data, dict):
            return None
        tag = str(data.get("tag_name") or "").strip()
        if not tag:
            return None
        assets = data.get("assets") if isinstance(data.get("assets"), list) else []
        filename, download = _pick_windows_asset(assets, tag)
        return {
            "version": tag.lstrip("vV"),
            "tag": tag,
            "filename": filename,
            "download": download,
            "html_url": str(data.get("html_url") or GITHUB_HTML_LATEST),
            "source": "github_releases",
        }
    except (OSError, ValueError, json.JSONDecodeError, requests.RequestException):
        return None


def _from_index_json(timeout: float) -> dict[str, Any] | None:
    for url in INDEX_URLS:
        try:
            r = requests.get(
                url,
                timeout=timeout,
                headers={"Accept": "application/json", "User-Agent": _UA},
            )
            if r.status_code != 200:
                continue
            data = r.json()
            win = data.get("windows_studio") if isinstance(data, dict) else None
            if not isinstance(win, dict) or not win.get("version"):
                continue
            download = (
                str(win.get("download") or "").strip()
                or str(win.get("github_release") or "").strip()
                or str(win.get("setup_github_release") or "").strip()
            )
            ver = str(win.get("version") or "").strip().lstrip("vV")
            return {
                "version": ver,
                "tag": "v" + ver,
                "filename": str(win.get("filename") or STABLE_EXE_NAMES[0]),
                "download": download,
                "html_url": GITHUB_HTML_LATEST,
                "source": "index_json",
            }
        except (OSError, ValueError, json.JSONDecodeError, requests.RequestException):
            continue
    return None


def fetch_windows_meta(timeout: float = 4.0) -> dict[str, Any] | None:
    """Métadonnées de la dernière Release Windows (GitHub d’abord, index en secours)."""
    return _from_github_api(timeout) or _from_index_json(timeout)


def get_update_status(force: bool = False, timeout: float = 4.0) -> dict[str, Any]:
    """
    Statut pour l’UI / l’API locale.
    Hors ligne ou erreur réseau → available=False, offline=True (pas de faux positif).
    """
    global _cache
    with _cache_lock:
        if _cache is not None and not force:
            return dict(_cache)

    local = APP_VERSION
    meta = fetch_windows_meta(timeout=timeout)
    if not meta:
        status = {
            "ok": True,
            "available": False,
            "offline": True,
            "local": local,
            "remote": "",
            "download": "",
            "html_url": GITHUB_HTML_LATEST,
            "source": "",
            "message": "",
        }
        with _cache_lock:
            _cache = dict(status)
        return status

    remote = str(meta.get("version") or "").strip()
    available = bool(remote) and is_newer(remote, local)
    download = str(meta.get("download") or "").strip()
    status = {
        "ok": True,
        "available": available,
        "offline": False,
        "local": local,
        "remote": remote,
        "download": download if available else "",
        "html_url": str(meta.get("html_url") or GITHUB_HTML_LATEST),
        "filename": str(meta.get("filename") or ""),
        "source": str(meta.get("source") or ""),
        "message": (
            f"Mise à jour {remote} disponible (vous avez {local})."
            if available
            else ""
        ),
    }
    with _cache_lock:
        _cache = dict(status)
    return status


def check_for_update(open_browser: bool = False) -> dict[str, Any] | None:
    """
    Si une version plus récente est publiée sur GitHub Releases, retourne le méta.
    N’ouvre le navigateur que si open_browser=True et qu’une URL existe.
    Hors ligne → None (aucun faux positif bloquant).
    """
    status = get_update_status(force=True)
    if not status.get("available"):
        return None
    download = str(status.get("download") or "").strip()
    if open_browser and download:
        try:
            webbrowser.open(download)
        except Exception:
            pass
    return {
        "version": status.get("remote"),
        "download": download,
        "html_url": status.get("html_url"),
        "filename": status.get("filename"),
        "source": status.get("source"),
    }
