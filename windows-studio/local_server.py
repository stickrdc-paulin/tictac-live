# -*- coding: utf-8 -*-
"""Serveur local : UI régie + proxy API WordPress authentifié."""
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
    SITE,
    clear_saved_cookies,
    cookies_header,
    login_wordpress,
    resolve_session,
    save_cookies,
)


def _ui_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "ui"
    return Path(__file__).resolve().parent / "ui"


UI_DIR = _ui_dir()


class StudioState:
    def __init__(self) -> None:
        self.cookies: dict[str, str] = {}
        self.lock = threading.Lock()

    def set_cookies(self, cookies: dict[str, str]) -> None:
        with self.lock:
            self.cookies = dict(cookies)

    def get_cookies(self) -> dict[str, str]:
        with self.lock:
            return dict(self.cookies)


STATE = StudioState()


class Handler(BaseHTTPRequestHandler):
    server_version = "TICTACStudio/1.0"

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
        if path in ("/", "/index.html"):
            return self._file(UI_DIR / "index.html", "text/html; charset=utf-8")
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

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/auth/check":
            return self._auth_check()
        if path == "/auth/login":
            return self._auth_login()
        if path == "/auth/logout":
            clear_saved_cookies()
            STATE.set_cookies({})
            return self._json(200, {"ok": True})
        if path in ("/api", "/api.php", "/direct/api.php"):
            return self._proxy_api()
        self._json(404, {"ok": False, "error": "Route inconnue"})

    def _auth_check(self) -> None:
        result = resolve_session()
        if result.get("ok") and result.get("cookies"):
            STATE.set_cookies(result["cookies"])
        self._json(
            200,
            {
                "ok": bool(result.get("ok")),
                "source": result.get("source") or "",
                "auth": result.get("auth") or {},
                "error": result.get("error") or "",
                "site": SITE,
            },
        )

    def _auth_login(self) -> None:
        body = self._read_json()
        user = str(body.get("username") or "").strip()
        password = str(body.get("password") or "")
        if not user or not password:
            return self._json(400, {"ok": False, "error": "Identifiant et mot de passe requis"})
        try:
            cookies, cfg = login_wordpress(user, password)
        except Exception as e:
            return self._json(502, {"ok": False, "error": f"Connexion impossible : {e}"})
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
        STATE.set_cookies(cookies)
        self._json(200, {"ok": True, "auth": auth, "source": "login"})

    def _proxy_api(self) -> None:
        body = self._read_json()
        cookies = STATE.get_cookies()
        if not cookies:
            return self._json(401, {"ok": False, "error": "Non connecté"})
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
            return self._json(502, {"ok": False, "error": str(e)})
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
