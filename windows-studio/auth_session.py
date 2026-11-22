# -*- coding: utf-8 -*-
"""Session WordPress pour TICTAC Studio Regie (cookies navigateur ou login)."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

import requests

SITE = "https://tictachebdo.cd"
API = SITE + "/direct/api.php"
LOGIN = SITE + "/wp-login.php"
DOMAIN = "tictachebdo.cd"

APP_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "TICTAC-Studio"
COOKIE_FILE = APP_DIR / "session.json"


def _load_app_version() -> str:
    """Lit windows-studio/VERSION (aussi embarqué dans le bundle PyInstaller)."""
    candidates = [
        Path(__file__).resolve().parent / "VERSION",
        Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "VERSION",
    ]
    for path in candidates:
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    return text.splitlines()[0].strip()
        except OSError:
            continue
    return "1.1.0"


APP_VERSION = _load_app_version()


def _ensure_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


def save_cookies(cookies: dict[str, str], source: str = "app") -> None:
    _ensure_dir()
    COOKIE_FILE.write_text(
        json.dumps({"cookies": cookies, "source": source, "version": APP_VERSION}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_saved_cookies() -> dict[str, str]:
    if not COOKIE_FILE.is_file():
        return {}
    try:
        data = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
        c = data.get("cookies") or {}
        return {str(k): str(v) for k, v in c.items()} if isinstance(c, dict) else {}
    except Exception:
        return {}


def clear_saved_cookies() -> None:
    try:
        COOKIE_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _cookie_paths() -> list[tuple[str, Path]]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    roaming = Path(os.environ.get("APPDATA", ""))
    home = Path.home()
    return [
        ("chrome", local / "Google" / "Chrome" / "User Data" / "Default" / "Network" / "Cookies"),
        ("chrome", local / "Google" / "Chrome" / "User Data" / "Default" / "Cookies"),
        ("edge", local / "Microsoft" / "Edge" / "User Data" / "Default" / "Network" / "Cookies"),
        ("edge", local / "Microsoft" / "Edge" / "User Data" / "Default" / "Cookies"),
        ("brave", local / "BraveSoftware" / "Brave-Browser" / "User Data" / "Default" / "Network" / "Cookies"),
        ("firefox", roaming / "Mozilla" / "Firefox" / "Profiles"),
        ("chrome", home / "AppData" / "Local" / "Google" / "Chrome" / "User Data" / "Default" / "Network" / "Cookies"),
    ]


def _load_jar_from_copy(loader: Callable[..., Any], cookie_file: Path) -> Any:
    """Copie la base cookies (Chrome/Edge souvent verrouillés) puis lit."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="tt_cookies_"))
    try:
        dest = tmp_dir / "Cookies"
        shutil.copy2(cookie_file, dest)
        # Fichier journal parfois requis
        for side in (cookie_file.parent / (cookie_file.name + "-journal"), cookie_file.with_suffix(".db-journal")):
            if side.is_file():
                try:
                    shutil.copy2(side, tmp_dir / side.name)
                except Exception:
                    pass
        return loader(cookie_file=str(dest), domain_name=DOMAIN)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def import_browser_cookies() -> tuple[dict[str, str], str]:
    """Lit les cookies tictachebdo.cd depuis Chrome / Edge / Brave / Firefox."""
    try:
        import browser_cookie3  # type: ignore
    except ImportError:
        return {}, ""

    loaders: list[tuple[str, Callable[..., Any]]] = [
        ("chrome", getattr(browser_cookie3, "chrome", None)),
        ("edge", getattr(browser_cookie3, "edge", None)),
        ("brave", getattr(browser_cookie3, "brave", None)),
        ("firefox", getattr(browser_cookie3, "firefox", None)),
        ("chromium", getattr(browser_cookie3, "chromium", None)),
    ]

    best: dict[str, str] = {}
    best_src = ""

    for name, fn in loaders:
        if not callable(fn):
            continue
        try:
            jar = fn(domain_name=DOMAIN)
        except Exception:
            jar = None
            # Tentative via copie du fichier Cookies (navigateur ouvert)
            for label, path in _cookie_paths():
                if label != name or not path.is_file():
                    continue
                try:
                    jar = _load_jar_from_copy(fn, path)
                    break
                except Exception:
                    continue
            if jar is None:
                continue

        merged: dict[str, str] = {}
        try:
            for c in jar:
                host = (getattr(c, "domain", "") or "").lstrip(".")
                if DOMAIN not in host:
                    continue
                merged[c.name] = c.value
        except Exception:
            continue

        if not merged:
            continue
        if any(k.startswith("wordpress_logged_in_") for k in merged):
            return merged, name
        if not best:
            best, best_src = merged, name

    return best, best_src


def cookies_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def api_config(cookies: dict[str, str]) -> dict[str, Any]:
    r = requests.post(
        API,
        json={"action": "config"},
        headers={"Cookie": cookies_header(cookies), "Content-Type": "application/json"},
        timeout=20,
    )
    try:
        data = r.json()
    except Exception:
        data = {"ok": False, "error": "Réponse invalide"}
    data["_http"] = r.status_code
    return data


def login_wordpress(username: str, password: str) -> tuple[dict[str, str], dict[str, Any]]:
    """Connexion WP classique ; retourne cookies + résultat config."""
    s = requests.Session()
    s.get(LOGIN, timeout=20)
    s.post(
        LOGIN,
        data={
            "log": username,
            "pwd": password,
            "wp-submit": "Log In",
            "redirect_to": SITE + "/direct/studio.php",
            "testcookie": "1",
        },
        timeout=30,
        allow_redirects=True,
    )
    cookies = {c.name: c.value for c in s.cookies}
    cfg = api_config(cookies)
    return cookies, cfg


def resolve_session() -> dict[str, Any]:
    """
    Ordre :
    1) session app sauvegardée
    2) cookies navigateur local (Chrome/Edge/Brave/Firefox)
    """
    # 1) saved
    saved = load_saved_cookies()
    if saved:
        try:
            cfg = api_config(saved)
        except Exception as e:
            cfg = {"ok": False, "error": str(e)}
        auth = (cfg.get("auth") or {}) if cfg.get("ok") else {}
        if auth.get("studio"):
            return {
                "ok": True,
                "cookies": saved,
                "source": "app",
                "auth": auth,
                "config": cfg,
            }
        # Session app expirée → on nettoie pour forcer le navigateur / login
        clear_saved_cookies()

    # 2) browser
    browser_cookies, browser_src = import_browser_cookies()
    if browser_cookies:
        try:
            cfg = api_config(browser_cookies)
        except Exception as e:
            cfg = {"ok": False, "error": str(e)}
        auth = (cfg.get("auth") or {}) if cfg.get("ok") else {}
        if auth.get("studio"):
            save_cookies(browser_cookies, source=f"browser:{browser_src}")
            return {
                "ok": True,
                "cookies": browser_cookies,
                "source": f"browser:{browser_src}",
                "auth": auth,
                "config": cfg,
            }
        if auth.get("loggedIn"):
            return {
                "ok": False,
                "cookies": browser_cookies,
                "source": f"browser:{browser_src}",
                "auth": auth,
                "error": "Session navigateur trouvée, mais ce compte n’est pas administrateur régie.",
                "config": cfg,
            }

    return {
        "ok": False,
        "cookies": {},
        "source": "",
        "auth": {},
        "error": "Aucune session admin ouverte. Connectez-vous.",
    }
