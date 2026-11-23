# -*- coding: utf-8 -*-
"""Serveur local : UI régie + proxy API WordPress authentifié + cache offline."""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests

from auth_session import (
    API,
    APP_VERSION,
    SITE,
    clear_all_local_session,
    cookies_header,
    load_config_cache,
    load_reporters_cache,
    login_wordpress,
    network_reachable,
    resolve_session,
    save_auth_cache,
    save_config_cache,
    save_cookies,
    save_reporters_cache,
    sync_reporters,
)


def _ui_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "ui"
    return Path(__file__).resolve().parent / "ui"


UI_DIR = _ui_dir()


class StudioState:
    def __init__(self) -> None:
        self.cookies: dict[str, str] = {}
        self.offline: bool = False
        self.lock = threading.Lock()

    def set_cookies(self, cookies: dict[str, str], *, offline: bool = False) -> None:
        with self.lock:
            self.cookies = dict(cookies)
            self.offline = offline

    def get_cookies(self) -> dict[str, str]:
        with self.lock:
            return dict(self.cookies)

    def is_offline(self) -> bool:
        with self.lock:
            return self.offline

    def set_offline(self, offline: bool) -> None:
        with self.lock:
            self.offline = offline


STATE = StudioState()


class Handler(BaseHTTPRequestHandler):
    server_version = f"TICTACStudio/{APP_VERSION}"

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(code, raw, "application/json; charset=utf-8")

    def _read_json(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/version":
            return self._json(200, {"ok": True, "version": APP_VERSION, "name": "TICTAC Studio Regie"})
        if path in ("/", "/index.html"):
            return self._index()
        if path == "/network/status":
            online = network_reachable()
            return self._json(
                200,
                {
                    "ok": True,
                    "network": online,
                    "online_status_available": online,
                    "version": APP_VERSION,
                },
            )
        if path == "/reporters/cache":
            return self._reporters_from_cache()
        if path.startswith("/ui/"):
            rel = unquote(path[4:])
        elif path.startswith("/"):
            rel = unquote(path.lstrip("/"))
        else:
            rel = ""
        # static under ui/
        candidate = (UI_DIR / rel).resolve()
        if str(candidate).startswith(str(UI_DIR.resolve())) and candidate.is_file():
            ctype = "application/octet-stream"
            if candidate.suffix == ".css":
                ctype = "text/css; charset=utf-8"
            elif candidate.suffix == ".js":
                ctype = "application/javascript; charset=utf-8"
            elif candidate.suffix == ".html":
                ctype = "text/html; charset=utf-8"
            elif candidate.suffix == ".svg":
                ctype = "image/svg+xml"
            return self._file(candidate, ctype)
        self._json(404, {"ok": False, "error": "Introuvable"})

    def _file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self._send(200, data, content_type)

    def _index(self) -> None:
        html = (UI_DIR / "index.html").read_text(encoding="utf-8")
        marker = "window.TT_STUDIO = { pin: '', maxMix: 3 };"
        injected = f"window.TT_STUDIO = {{ pin: '', maxMix: 3, version: {json.dumps(APP_VERSION)} }};"
        if marker in html:
            html = html.replace(marker, injected, 1)
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/auth/check":
            return self._auth_check()
        if path == "/auth/login":
            return self._auth_login()
        if path == "/auth/logout":
            clear_all_local_session()
            STATE.set_cookies({}, offline=False)
            return self._json(200, {"ok": True})
        if path == "/reporters/sync":
            return self._reporters_sync()
        if path in ("/api", "/api.php", "/direct/api.php"):
            return self._proxy_api()
        self._json(404, {"ok": False, "error": "Route inconnue"})

    def _auth_check(self) -> None:
        result = resolve_session()
        if result.get("ok") and result.get("cookies"):
            STATE.set_cookies(result["cookies"], offline=bool(result.get("offline")))
        self._json(
            200,
            {
                "ok": bool(result.get("ok")),
                "offline": bool(result.get("offline")),
                "network": bool(result.get("network")),
                "source": result.get("source") or "",
                "auth": result.get("auth") or {},
                "error": result.get("error") or "",
                "site": SITE,
                "version": APP_VERSION,
            },
        )

    def _auth_login(self) -> None:
        body = self._read_json()
        user = str(body.get("username") or "").strip()
        password = str(body.get("password") or "")
        if not user or not password:
            return self._json(400, {"ok": False, "error": "Identifiant et mot de passe requis"})
        if not network_reachable():
            return self._json(
                503,
                {
                    "ok": False,
                    "error": "Connexion internet requise pour le login. L’app peut s’ouvrir hors ligne seulement après une première connexion réussie.",
                    "network": False,
                },
            )
        try:
            cookies, cfg = login_wordpress(user, password)
        except Exception as e:
            return self._json(502, {"ok": False, "error": f"Connexion impossible : {e}", "network": True})
        auth = (cfg.get("auth") or {}) if cfg.get("ok") else {}
        if not auth.get("studio"):
            return self._json(
                403,
                {
                    "ok": False,
                    "error": "Compte connecté, mais sans droit régie (administrateur requis).",
                    "auth": auth,
                },
            )
        save_cookies(cookies, source="login")
        save_auth_cache(auth, source="login")
        save_config_cache(cfg)
        STATE.set_cookies(cookies, offline=False)
        # Extraire / mettre en cache la liste des reporteurs dès le login
        sync_result = sync_reporters(cookies)
        self._json(
            200,
            {
                "ok": True,
                "auth": auth,
                "source": "login",
                "offline": False,
                "network": True,
                "reporters_sync": {
                    "ok": bool(sync_result.get("ok")),
                    "count": len(sync_result.get("reporters") or []),
                    "error": sync_result.get("error") or "",
                },
            },
        )

    def _reporters_from_cache(self) -> None:
        cache = load_reporters_cache()
        online = network_reachable()
        reporters = cache.get("reporters") or []
        # Hors ligne : pas de statut live
        if not online:
            stripped = []
            for r in reporters:
                if not isinstance(r, dict):
                    continue
                item = dict(r)
                item.pop("online_for", None)
                item["online"] = False
                item["presence_unknown"] = True
                stripped.append(item)
            reporters = stripped
        self._json(
            200,
            {
                "ok": True,
                "from_cache": True,
                "network": online,
                "online_status_available": online,
                "reporters": reporters,
                "max_mix": cache.get("max_mix"),
                "saved_at": cache.get("saved_at"),
            },
        )

    def _reporters_sync(self) -> None:
        cookies = STATE.get_cookies()
        if not cookies:
            return self._json(401, {"ok": False, "error": "Non connecté"})
        result = sync_reporters(cookies)
        STATE.set_offline(not bool(result.get("network")))
        code = 200 if result.get("ok") else 502
        self._json(code, result)

    def _cached_config_response(self) -> dict[str, Any]:
        cfg = load_config_cache()
        if not cfg:
            return {
                "ok": False,
                "error": "Aucune config en cache. Connectez-vous une fois avec internet.",
                "from_cache": True,
                "network": False,
                "online_status_available": False,
            }
        out = dict(cfg)
        out["ok"] = True
        out["from_cache"] = True
        out["network"] = False
        out["online_status_available"] = False
        out["offline"] = True
        return out

    def _cached_list_response(self) -> dict[str, Any]:
        cache = load_reporters_cache()
        reporters = []
        for r in cache.get("reporters") or []:
            if not isinstance(r, dict):
                continue
            item = dict(r)
            item.pop("online_for", None)
            item["online"] = False
            item["presence_unknown"] = True
            reporters.append(item)
        return {
            "ok": True,
            "from_cache": True,
            "network": False,
            "online_status_available": False,
            "reporters": reporters,
            "max_mix": cache.get("max_mix") or 3,
            "saved_at": cache.get("saved_at"),
            "offline": True,
        }

    def _proxy_api(self) -> None:
        body = self._read_json()
        action = str(body.get("action") or "")
        cookies = STATE.get_cookies()
        if not cookies:
            return self._json(401, {"ok": False, "error": "Non connecté"})

        # Hors ligne : servir le cache pour config / list_reporters
        if not network_reachable():
            STATE.set_offline(True)
            if action == "config":
                return self._json(200, self._cached_config_response())
            if action == "list_reporters":
                return self._json(200, self._cached_list_response())
            return self._json(
                503,
                {
                    "ok": False,
                    "error": "Réseau indisponible. Login et sync exigent une connexion ; le statut en ligne des reporteurs aussi.",
                    "network": False,
                    "online_status_available": False,
                    "offline": True,
                },
            )

        STATE.set_offline(False)
        try:
            r = requests.post(
                API,
                json=body,
                headers={
                    "Cookie": cookies_header(cookies),
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=30,
            )
        except Exception as e:
            STATE.set_offline(True)
            if action == "config":
                return self._json(200, self._cached_config_response())
            if action == "list_reporters":
                payload = self._cached_list_response()
                payload["error"] = str(e)
                return self._json(200, payload)
            return self._json(502, {"ok": False, "error": str(e), "network": False})

        # Mettre en cache les réponses utiles
        try:
            data = r.json()
        except Exception:
            data = None

        if isinstance(data, dict) and data.get("ok"):
            if action == "config":
                auth = data.get("auth") or {}
                if isinstance(auth, dict) and auth.get("studio"):
                    save_auth_cache(auth, source="api")
                save_config_cache(data)
            elif action == "list_reporters":
                reporters = data.get("reporters") or []
                if isinstance(reporters, list):
                    max_mix = data.get("max_mix")
                    save_reporters_cache(
                        reporters,
                        max_mix=max_mix if isinstance(max_mix, int) else None,
                    )
                data = dict(data)
                data["from_cache"] = False
                data["network"] = True
                data["online_status_available"] = True
                raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(r.status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(raw)
                return

        # Relayer le JSON tel quel
        raw = r.content
        self.send_response(r.status_code)
        self.send_header("Content-Type", r.headers.get("Content-Type", "application/json; charset=utf-8"))
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)


def start_server(port: int = 0) -> tuple[ThreadingHTTPServer, int]:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    host, real_port = httpd.server_address
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, int(real_port)
