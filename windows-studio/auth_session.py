# -*- coding: utf-8 -*-
"""Session WordPress pour TICTAC Studio Regie (cookies navigateur ou login)."""
from __future__ import annotations

import json
import os
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

SITE = "https://tictachebdo.cd"
API = SITE + "/direct/api.php"
LOGIN = SITE + "/wp-login.php"
DOMAIN = "tictachebdo.cd"

APP_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "TICTAC-Studio"
COOKIE_FILE = APP_DIR / "session.json"


def _ensure_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


def save_cookies(cookies: dict[str, str], source: str = "app") -> None:
    _ensure_dir()
    COOKIE_FILE.write_text(
        json.dumps({"cookies": cookies, "source": source}, ensure_ascii=False, indent=2),
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


def import_browser_cookies() -> tuple[dict[str, str], str]:
    """Lit les cookies tictachebdo.cd depuis Chrome / Edge / Firefox (si ouverts)."""
    try:
        import browser_cookie3  # type: ignore
    except ImportError:
        return {}, ""

    loaders = [
        ("chrome", getattr(browser_cookie3, "chrome", None)),
        ("edge", getattr(browser_cookie3, "edge", None)),
        ("firefox", getattr(browser_cookie3, "firefox", None)),
    ]
    merged: dict[str, str] = {}
    source = ""
    for name, fn in loaders:
        if not callable(fn):
            continue
        try:
            jar = fn(domain_name=DOMAIN)
            got = False
            for c in jar:
                host = (c.domain or "").lstrip(".")
                if DOMAIN not in host:
                    continue
                merged[c.name] = c.value
                got = True
            if got and any(k.startswith("wordpress_logged_in_") for k in merged):
                source = name
                break
            if got and not source:
                source = name
        except Exception:
            continue
    return merged, source


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
    # Domaine parfois .tictachebdo.cd
    cfg = api_config(cookies)
    return cookies, cfg


def resolve_session() -> dict[str, Any]:
    """
    Ordre :
    1) session app sauvegardée
    2) cookies navigateur local (Chrome/Edge/Firefox)
    """
    # 1) saved
    saved = load_saved_cookies()
    if saved:
        cfg = api_config(saved)
        auth = (cfg.get("auth") or {}) if cfg.get("ok") else {}
        if auth.get("studio"):
            return {
                "ok": True,
                "cookies": saved,
                "source": "app",
                "auth": auth,
                "config": cfg,
            }

    # 2) browser
    browser_cookies, browser_src = import_browser_cookies()
    if browser_cookies:
        cfg = api_config(browser_cookies)
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
