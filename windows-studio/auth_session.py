# -*- coding: utf-8 -*-
"""Session WordPress pour TICTAC Studio Regie (cookies navigateur ou login)."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import requests

SITE = "https://tictachebdo.cd"
API = SITE + "/direct/api.php"
LOGIN = SITE + "/wp-login.php"
DOMAIN = "tictachebdo.cd"

APP_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "TICTAC-Studio"
COOKIE_FILE = APP_DIR / "session.json"
AUTH_CACHE_FILE = APP_DIR / "auth_cache.json"
REPORTERS_CACHE_FILE = APP_DIR / "reporters_cache.json"
CONFIG_CACHE_FILE = APP_DIR / "config_cache.json"


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


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_dir()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_cookies(cookies: dict[str, str], source: str = "app") -> None:
    _write_json(
        COOKIE_FILE,
        {"cookies": cookies, "source": source, "version": APP_VERSION},
    )


def load_saved_cookies() -> dict[str, str]:
    data = _read_json(COOKIE_FILE)
    c = data.get("cookies") or {}
    return {str(k): str(v) for k, v in c.items()} if isinstance(c, dict) else {}


def clear_saved_cookies() -> None:
    try:
        COOKIE_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def save_auth_cache(auth: dict[str, Any], source: str = "") -> None:
    _write_json(
        AUTH_CACHE_FILE,
        {
            "auth": auth,
            "source": source,
            "saved_at": time.time(),
            "version": APP_VERSION,
        },
    )


def load_auth_cache() -> dict[str, Any]:
    return _read_json(AUTH_CACHE_FILE)


def clear_auth_cache() -> None:
    try:
        AUTH_CACHE_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def save_config_cache(config: dict[str, Any]) -> None:
    # Ne pas stocker les cookies ni données sensibles inutiles
    slim = {
        k: v
        for k, v in config.items()
        if k not in ("_http",)
    }
    _write_json(
        CONFIG_CACHE_FILE,
        {"config": slim, "saved_at": time.time(), "version": APP_VERSION},
    )


def load_config_cache() -> dict[str, Any]:
    data = _read_json(CONFIG_CACHE_FILE)
    cfg = data.get("config")
    return cfg if isinstance(cfg, dict) else {}


def save_reporters_cache(
    reporters: list[dict[str, Any]],
    *,
    max_mix: int | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Met en cache la liste des reporteurs (identité), sans dépendre du statut live."""
    slim: list[dict[str, Any]] = []
    for r in reporters:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id") or "").strip()
        if not rid:
            continue
        entry: dict[str, Any] = {
            "id": rid,
            "name": str(r.get("name") or r.get("display_name") or rid),
        }
        for key in ("login", "email", "avatar", "role"):
            if r.get(key) is not None:
                entry[key] = r.get(key)
        slim.append(entry)
    payload: dict[str, Any] = {
        "reporters": slim,
        "saved_at": time.time(),
        "version": APP_VERSION,
    }
    if max_mix is not None:
        payload["max_mix"] = int(max_mix)
    if meta:
        payload["meta"] = meta
    _write_json(REPORTERS_CACHE_FILE, payload)


def load_reporters_cache() -> dict[str, Any]:
    data = _read_json(REPORTERS_CACHE_FILE)
    reporters = data.get("reporters")
    if not isinstance(reporters, list):
        data["reporters"] = []
    return data


def clear_all_local_session() -> None:
    clear_saved_cookies()
    clear_auth_cache()
    try:
        CONFIG_CACHE_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def network_reachable(timeout: float = 2.5) -> bool:
    """
    True si le PC peut joindre tictachebdo.cd (internet) ou au moins
    résoudre / tenter une connexion TCP — utilisé pour savoir si le statut
    « en ligne » des reporteurs est interrogeable.
    """
    try:
        r = requests.head(SITE, timeout=timeout, allow_redirects=True)
        return r.status_code < 500
    except Exception:
        pass
    try:
        r = requests.get(SITE, timeout=timeout, allow_redirects=True)
        return True
    except Exception:
        return False


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


def api_list_reporters(cookies: dict[str, str]) -> dict[str, Any]:
    r = requests.post(
        API,
        json={"action": "list_reporters"},
        headers={"Cookie": cookies_header(cookies), "Content-Type": "application/json"},
        timeout=30,
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


def _offline_session(cookies: dict[str, str], source: str) -> dict[str, Any] | None:
    """Si une session + auth régie sont en cache, autorise l’ouverture hors ligne."""
    cached = load_auth_cache()
    auth = cached.get("auth") if isinstance(cached.get("auth"), dict) else {}
    if not auth.get("studio"):
        return None
    return {
        "ok": True,
        "offline": True,
        "network": False,
        "cookies": cookies,
        "source": source or cached.get("source") or "cache",
        "auth": auth,
        "config": load_config_cache(),
        "error": "",
    }


def resolve_session() -> dict[str, Any]:
    """
    Ordre :
    1) session app sauvegardée (en ligne → valide ; hors ligne → cache auth)
    2) cookies navigateur local (Chrome/Edge/Brave/Firefox) — nécessite le réseau
    """
    online = network_reachable()

    # 1) saved
    saved = load_saved_cookies()
    if saved:
        if online:
            try:
                cfg = api_config(saved)
            except Exception as e:
                # Réseau tombé pendant l’appel → fallback offline
                offline = _offline_session(saved, "app")
                if offline:
                    offline["error"] = str(e)
                    return offline
                cfg = {"ok": False, "error": str(e)}
            auth = (cfg.get("auth") or {}) if cfg.get("ok") else {}
            if auth.get("studio"):
                save_auth_cache(auth, source="app")
                save_config_cache(cfg)
                return {
                    "ok": True,
                    "offline": False,
                    "network": True,
                    "cookies": saved,
                    "source": "app",
                    "auth": auth,
                    "config": cfg,
                }
            # Session app expirée (réponse serveur) → on nettoie
            clear_saved_cookies()
            clear_auth_cache()
        else:
            offline = _offline_session(saved, "app")
            if offline:
                return offline

    # 2) browser — uniquement si réseau (validation serveur obligatoire)
    if online:
        browser_cookies, browser_src = import_browser_cookies()
        if browser_cookies:
            try:
                cfg = api_config(browser_cookies)
            except Exception as e:
                cfg = {"ok": False, "error": str(e)}
            auth = (cfg.get("auth") or {}) if cfg.get("ok") else {}
            if auth.get("studio"):
                save_cookies(browser_cookies, source=f"browser:{browser_src}")
                save_auth_cache(auth, source=f"browser:{browser_src}")
                save_config_cache(cfg)
                return {
                    "ok": True,
                    "offline": False,
                    "network": True,
                    "cookies": browser_cookies,
                    "source": f"browser:{browser_src}",
                    "auth": auth,
                    "config": cfg,
                }
            if auth.get("loggedIn"):
                return {
                    "ok": False,
                    "offline": False,
                    "network": True,
                    "cookies": browser_cookies,
                    "source": f"browser:{browser_src}",
                    "auth": auth,
                    "error": "Session navigateur trouvée, mais ce compte n’est pas administrateur régie.",
                    "config": cfg,
                }

    return {
        "ok": False,
        "offline": not online,
        "network": online,
        "cookies": {},
        "source": "",
        "auth": {},
        "error": (
            "Hors ligne : aucune session régie en cache. Connectez-vous une fois avec internet."
            if not online
            else "Aucune session admin ouverte. Connectez-vous."
        ),
    }


def sync_reporters(cookies: dict[str, str]) -> dict[str, Any]:
    """
    Tire la liste des reporteurs depuis l’API et met à jour le cache local.
    Exige le réseau. Le statut « en ligne » n’est fiable que si le PC a
    internet ou LAN et que l’app reporteur tourne sur le téléphone.
    """
    if not cookies:
        return {"ok": False, "error": "Non connecté", "network": False}
    if not network_reachable():
        cache = load_reporters_cache()
        return {
            "ok": True,
            "from_cache": True,
            "network": False,
            "online_status_available": False,
            "reporters": cache.get("reporters") or [],
            "max_mix": cache.get("max_mix"),
            "saved_at": cache.get("saved_at"),
            "error": "Pas de réseau : liste cache affichée, statut en ligne indisponible.",
        }
    try:
        data = api_list_reporters(cookies)
    except Exception as e:
        cache = load_reporters_cache()
        return {
            "ok": bool(cache.get("reporters")),
            "from_cache": True,
            "network": False,
            "online_status_available": False,
            "reporters": cache.get("reporters") or [],
            "max_mix": cache.get("max_mix"),
            "saved_at": cache.get("saved_at"),
            "error": str(e),
        }
    if not data.get("ok"):
        return {
            "ok": False,
            "network": True,
            "online_status_available": True,
            "error": data.get("error") or "Synchronisation reporteurs refusée",
            "_http": data.get("_http"),
        }
    reporters = data.get("reporters") or []
    if not isinstance(reporters, list):
        reporters = []
    max_mix = data.get("max_mix")
    save_reporters_cache(reporters, max_mix=max_mix if isinstance(max_mix, int) else None)
    return {
        "ok": True,
        "from_cache": False,
        "network": True,
        "online_status_available": True,
        "reporters": reporters,
        "max_mix": max_mix,
        "saved_at": time.time(),
    }
