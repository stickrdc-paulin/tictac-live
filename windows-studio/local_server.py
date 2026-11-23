# -*- coding: utf-8 -*-
"""Serveur local : UI régie + proxy API WordPress + radio locale (config / playlists / jingles)."""
from __future__ import annotations

import json
import mimetypes
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests

from auth_session import (
    API,
    APP_DIR,
    SITE,
    clear_saved_cookies,
    cookies_header,
    login_wordpress,
    resolve_session,
    save_cookies,
)
from radio_engine import ENGINE, find_ffmpeg, test_stream_endpoint
from radio_store import (
    create_playlist,
    delete_media,
    get_active_playlist,
    import_media_file,
    list_media,
    load_jingle_schedule,
    load_playlists,
    load_stream_config,
    public_stream_config,
    resolve_media_path,
    get_media,
    save_stream_config,
    set_active_playlist,
    update_jingle_schedule,
    update_playlist,
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
    server_version = "TICTACStudio/1.2"

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
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            return self._file(UI_DIR / "index.html", "text/html; charset=utf-8")
        if path == "/stream/config":
            return self._json(200, {"ok": True, "config": public_stream_config()})
        if path == "/stream/status":
            return self._json(200, ENGINE.status())
        if path == "/media":
            qs = parse_qs(parsed.query)
            kind = (qs.get("kind") or [None])[0]
            return self._json(200, {"ok": True, "items": list_media(kind=kind)})
        if path.startswith("/media/file/"):
            return self._media_file(unquote(path[len("/media/file/") :]))
        if path == "/playlists":
            data = load_playlists()
            return self._json(200, {"ok": True, **data, "active": get_active_playlist()})
        if path == "/jingles/schedule":
            return self._json(200, {"ok": True, "schedule": load_jingle_schedule()})
        if path == "/radio/status":
            return self._json(200, ENGINE.status())

        if path.startswith("/ui/"):
            rel = unquote(path[4:])
        elif path.startswith("/"):
            rel = unquote(path.lstrip("/"))
        else:
            rel = ""
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

    def _media_file(self, media_id: str) -> None:
        item = get_media(media_id)
        if not item:
            return self._json(404, {"ok": False, "error": "Média introuvable"})
        path = resolve_media_path(item)
        if not path:
            return self._json(404, {"ok": False, "error": "Fichier manquant"})
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        return self._file(path, ctype)

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

        # —— Radio locale (pas de WP) ——
        if path == "/stream/config":
            return self._stream_config_save()
        if path == "/stream/test":
            return self._stream_test()
        if path == "/stream/start":
            return self._json(200, ENGINE.start_stream())
        if path == "/stream/stop":
            return self._json(200, ENGINE.stop_stream())
        if path == "/radio/play":
            body = self._read_json()
            return self._json(200, ENGINE.play(stream=bool(body.get("stream"))))
        if path == "/radio/stop":
            return self._json(200, ENGINE.stop())
        if path == "/radio/skip":
            return self._json(200, ENGINE.skip())
        if path == "/radio/pause":
            return self._json(200, ENGINE.pause())
        if path == "/media/import":
            return self._media_import()
        if path == "/media/delete":
            return self._media_delete()
        if path == "/playlists/update":
            return self._playlist_update()
        if path == "/playlists/mode":
            return self._playlist_mode()
        if path == "/playlists/active":
            return self._playlist_active()
        if path == "/playlists/create":
            return self._playlist_create()
        if path == "/jingles/schedule":
            return self._jingles_schedule_save()
        if path == "/jingles/fire":
            return self._jingles_fire()

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
        if not user or password == "":
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
        raw = r.content
        self.send_response(r.status_code)
        self.send_header("Content-Type", r.headers.get("Content-Type", "application/json; charset=utf-8"))
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _stream_config_save(self) -> None:
        body = self._read_json()
        cfg = save_stream_config(body.get("config") or body)
        pub = public_stream_config()
        ffmpeg = find_ffmpeg(str(cfg.get("ffmpeg_path") or ""))
        self._json(200, {"ok": True, "config": pub, "ffmpeg_found": bool(ffmpeg)})

    def _stream_test(self) -> None:
        body = self._read_json()
        if body.get("config"):
            # Test temporaire sans forcément sauver le password masqué
            cfg = load_stream_config()
            tmp = dict(cfg)
            for k, v in (body.get("config") or {}).items():
                if k == "password" and (not v or v == "••••••••"):
                    continue
                tmp[k] = v
            result = test_stream_endpoint(tmp)
        else:
            result = test_stream_endpoint(load_stream_config())
        code = 200 if result.get("ok") else 502
        self._json(code, result)

    def _media_import(self) -> None:
        body = self._read_json()
        src = str(body.get("path") or "").strip()
        kind = str(body.get("kind") or "song")
        title = body.get("title")
        if not src:
            return self._json(400, {"ok": False, "error": "Chemin fichier requis"})
        try:
            item = import_media_file(src, kind=kind, title=str(title) if title else None)
        except FileNotFoundError as e:
            return self._json(404, {"ok": False, "error": str(e)})
        except ValueError as e:
            return self._json(400, {"ok": False, "error": str(e)})
        except Exception as e:
            return self._json(500, {"ok": False, "error": str(e)})
        self._json(200, {"ok": True, "item": item})

    def _media_delete(self) -> None:
        body = self._read_json()
        mid = str(body.get("id") or "").strip()
        if not mid:
            return self._json(400, {"ok": False, "error": "id requis"})
        ok = delete_media(mid)
        self._json(200 if ok else 404, {"ok": ok, "error": "" if ok else "Introuvable"})

    def _playlist_update(self) -> None:
        body = self._read_json()
        pid = str(body.get("id") or (get_active_playlist() or {}).get("id") or "").strip()
        try:
            pl = update_playlist(pid, body)
        except KeyError:
            return self._json(404, {"ok": False, "error": "Playlist introuvable"})
        self._json(200, {"ok": True, "playlist": pl})

    def _playlist_mode(self) -> None:
        body = self._read_json()
        pid = str(body.get("id") or (get_active_playlist() or {}).get("id") or "").strip()
        try:
            pl = update_playlist(pid, {"play_mode": body.get("play_mode")})
        except KeyError:
            return self._json(404, {"ok": False, "error": "Playlist introuvable"})
        self._json(200, {"ok": True, "playlist": pl})

    def _playlist_active(self) -> None:
        body = self._read_json()
        pid = str(body.get("id") or "").strip()
        try:
            pl = set_active_playlist(pid)
        except KeyError:
            return self._json(404, {"ok": False, "error": "Playlist introuvable"})
        self._json(200, {"ok": True, "playlist": pl})

    def _playlist_create(self) -> None:
        body = self._read_json()
        pl = create_playlist(str(body.get("name") or "Playlist"))
        self._json(200, {"ok": True, "playlist": pl})

    def _jingles_schedule_save(self) -> None:
        body = self._read_json()
        sched = update_jingle_schedule(body.get("schedule") or body)
        self._json(200, {"ok": True, "schedule": sched})

    def _jingles_fire(self) -> None:
        body = self._read_json()
        mid = str(body.get("id") or "").strip()
        result = ENGINE.fire_jingle(mid)
        code = 200 if result.get("ok") else 400
        self._json(code, result)


def start_server(port: int = 0) -> tuple[ThreadingHTTPServer, int]:
    # Garantir dossiers média
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    host, real_port = httpd.server_address
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, int(real_port)
