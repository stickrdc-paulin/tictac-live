# -*- coding: utf-8 -*-
"""Stockage local radio (config encodeur, médiathèque, playlists, jingles).

Fichiers sous %LOCALAPPDATA%\\TICTAC-Studio\\ — secrets jamais envoyés au site.
"""
from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from auth_session import APP_DIR

STREAM_CONFIG_FILE = APP_DIR / "stream_config.json"
MEDIA_LIBRARY_FILE = APP_DIR / "media_library.json"
PLAYLISTS_FILE = APP_DIR / "playlists.json"
JINGLE_SCHEDULE_FILE = APP_DIR / "jingle_schedule.json"
MEDIA_MUSIC_DIR = APP_DIR / "media" / "music"
MEDIA_JINGLES_DIR = APP_DIR / "media" / "jingles"

DEFAULT_STREAM: dict[str, Any] = {
    "version": 1,
    "protocol": "icecast",
    "host": "video2.getstreamhosting.com",
    "port": 8000,
    "mount": "/stream",
    "username": "source",
    "password": "",
    "bitrate_kbps": 128,
    "format": "mp3",
    "ssl": False,
    "ffmpeg_path": "",
    "updated_at": 0,
}

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"}


def _ensure_dirs() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_JINGLES_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_dirs()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _safe_filename(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^\w.\- ()\[\]]+", "_", base, flags=re.UNICODE).strip("._")
    return base or f"audio_{uuid.uuid4().hex[:8]}"


# —— Stream config ——


def load_stream_config() -> dict[str, Any]:
    data = _read_json(STREAM_CONFIG_FILE)
    out = dict(DEFAULT_STREAM)
    if data:
        out.update({k: data[k] for k in DEFAULT_STREAM if k in data})
    return out


def save_stream_config(updates: dict[str, Any]) -> dict[str, Any]:
    cfg = load_stream_config()
    for key in (
        "protocol",
        "host",
        "port",
        "mount",
        "username",
        "password",
        "bitrate_kbps",
        "format",
        "ssl",
        "ffmpeg_path",
    ):
        if key not in updates:
            continue
        val = updates[key]
        if key == "port":
            try:
                cfg[key] = int(val)
            except (TypeError, ValueError):
                continue
        elif key == "bitrate_kbps":
            try:
                cfg[key] = max(32, min(320, int(val)))
            except (TypeError, ValueError):
                continue
        elif key == "ssl":
            cfg[key] = bool(val)
        elif key == "protocol":
            p = str(val or "icecast").lower().strip()
            if p not in ("icecast", "shoutcast", "shoutcast1", "shoutcast2"):
                p = "icecast"
            cfg[key] = "shoutcast" if p.startswith("shoutcast") else "icecast"
        elif key == "password":
            # Chaîne vide = ne pas écraser (UI masquée)
            if val is None:
                continue
            s = str(val)
            if s == "" or s == "••••••••":
                continue
            cfg[key] = s
        else:
            cfg[key] = str(val or "").strip()
    mount = str(cfg.get("mount") or "/stream").strip() or "/stream"
    if not mount.startswith("/"):
        mount = "/" + mount
    cfg["mount"] = mount
    cfg["version"] = 1
    cfg["updated_at"] = time.time()
    _write_json(STREAM_CONFIG_FILE, cfg)
    return cfg


def public_stream_config() -> dict[str, Any]:
    """Config sans password en clair (indicateur has_password seulement)."""
    cfg = load_stream_config()
    out = dict(cfg)
    pw = str(out.pop("password", "") or "")
    out["has_password"] = bool(pw)
    out["password"] = "••••••••" if pw else ""
    return out


# —— Media library ——


def _default_library() -> dict[str, Any]:
    return {"version": 1, "items": []}


def load_media_library() -> dict[str, Any]:
    data = _read_json(MEDIA_LIBRARY_FILE)
    if not data:
        return _default_library()
    items = data.get("items")
    if not isinstance(items, list):
        data["items"] = []
    data["version"] = 1
    return data


def save_media_library(lib: dict[str, Any]) -> None:
    lib["version"] = 1
    _write_json(MEDIA_LIBRARY_FILE, lib)


def list_media(*, kind: str | None = None) -> list[dict[str, Any]]:
    items = load_media_library().get("items") or []
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if kind and it.get("kind") != kind:
            continue
        out.append(dict(it))
    return out


def get_media(media_id: str) -> dict[str, Any] | None:
    mid = str(media_id or "").strip()
    for it in list_media():
        if it.get("id") == mid:
            return it
    return None


def resolve_media_path(item: dict[str, Any]) -> Path | None:
    rel = str(item.get("path") or "").strip()
    if not rel:
        return None
    path = (APP_DIR / rel).resolve()
    try:
        path.relative_to(APP_DIR.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def import_media_file(src: str | Path, *, kind: str = "song", title: str | None = None) -> dict[str, Any]:
    _ensure_dirs()
    kind = "jingle" if kind == "jingle" else "song"
    source = Path(src).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"Fichier introuvable : {source}")
    if source.suffix.lower() not in AUDIO_EXTS:
        raise ValueError(f"Extension non supportée : {source.suffix}")
    dest_dir = MEDIA_JINGLES_DIR if kind == "jingle" else MEDIA_MUSIC_DIR
    safe = _safe_filename(source.name)
    dest = dest_dir / safe
    if dest.exists():
        stem, suf = dest.stem, dest.suffix
        dest = dest_dir / f"{stem}_{uuid.uuid4().hex[:6]}{suf}"
    shutil.copy2(source, dest)
    rel = str(dest.relative_to(APP_DIR)).replace("\\", "/")
    item = {
        "id": _new_id("m"),
        "path": rel,
        "title": (title or source.stem).strip() or safe,
        "duration_ms": 0,
        "kind": kind,
        "added_at": time.time(),
    }
    lib = load_media_library()
    items = list(lib.get("items") or [])
    items.append(item)
    lib["items"] = items
    save_media_library(lib)
    return item


def delete_media(media_id: str) -> bool:
    lib = load_media_library()
    items = [it for it in (lib.get("items") or []) if isinstance(it, dict)]
    target = None
    kept: list[dict[str, Any]] = []
    for it in items:
        if it.get("id") == media_id:
            target = it
        else:
            kept.append(it)
    if not target:
        return False
    path = resolve_media_path(target)
    if path and path.is_file():
        try:
            path.unlink()
        except Exception:
            pass
    lib["items"] = kept
    save_media_library(lib)
    # Retirer des playlists
    pl = load_playlists()
    changed = False
    for p in pl.get("playlists") or []:
        if not isinstance(p, dict):
            continue
        before = list(p.get("items") or [])
        after = [x for x in before if isinstance(x, dict) and x.get("media_id") != media_id]
        if len(after) != len(before):
            p["items"] = after
            changed = True
    if changed:
        save_playlists(pl)
    # Retirer des pools jingles
    sched = load_jingle_schedule()
    bt = sched.get("between_tracks") or {}
    if isinstance(bt, dict) and media_id in (bt.get("jingle_ids") or []):
        bt["jingle_ids"] = [x for x in (bt.get("jingle_ids") or []) if x != media_id]
        sched["between_tracks"] = bt
        save_jingle_schedule(sched)
    clock = sched.get("clock") or []
    new_clock = []
    for entry in clock:
        if not isinstance(entry, dict):
            continue
        ids = [x for x in (entry.get("jingle_ids") or []) if x != media_id]
        entry = dict(entry)
        entry["jingle_ids"] = ids
        new_clock.append(entry)
    sched["clock"] = new_clock
    save_jingle_schedule(sched)
    return True


# —— Playlists ——


def _default_playlists() -> dict[str, Any]:
    return {
        "version": 1,
        "active_playlist_id": "pl_default",
        "playlists": [
            {
                "id": "pl_default",
                "name": "Antenne",
                "loop": True,
                "play_mode": "sequential",
                "random_avoid_recent": 5,
                "items": [],
            }
        ],
    }


def load_playlists() -> dict[str, Any]:
    data = _read_json(PLAYLISTS_FILE)
    if not data or not isinstance(data.get("playlists"), list) or not data["playlists"]:
        data = _default_playlists()
        save_playlists(data)
        return data
    data["version"] = 1
    if not data.get("active_playlist_id"):
        data["active_playlist_id"] = data["playlists"][0].get("id") or "pl_default"
    for p in data["playlists"]:
        if not isinstance(p, dict):
            continue
        if p.get("play_mode") not in ("sequential", "random", "shuffle_cycle"):
            p["play_mode"] = "sequential"
        if "loop" not in p:
            p["loop"] = True
        if "random_avoid_recent" not in p:
            p["random_avoid_recent"] = 5
        if not isinstance(p.get("items"), list):
            p["items"] = []
    return data


def save_playlists(data: dict[str, Any]) -> None:
    data["version"] = 1
    _write_json(PLAYLISTS_FILE, data)


def get_active_playlist() -> dict[str, Any]:
    data = load_playlists()
    aid = data.get("active_playlist_id")
    for p in data.get("playlists") or []:
        if isinstance(p, dict) and p.get("id") == aid:
            return p
    playlists = [p for p in (data.get("playlists") or []) if isinstance(p, dict)]
    return playlists[0] if playlists else _default_playlists()["playlists"][0]


def update_playlist(playlist_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    data = load_playlists()
    found = None
    for p in data.get("playlists") or []:
        if not isinstance(p, dict) or p.get("id") != playlist_id:
            continue
        if "name" in updates:
            p["name"] = str(updates["name"] or p.get("name") or "Playlist").strip()
        if "loop" in updates:
            p["loop"] = bool(updates["loop"])
        if "play_mode" in updates:
            mode = str(updates["play_mode"] or "sequential")
            if mode not in ("sequential", "random", "shuffle_cycle"):
                mode = "sequential"
            p["play_mode"] = mode
        if "random_avoid_recent" in updates:
            try:
                p["random_avoid_recent"] = max(0, int(updates["random_avoid_recent"]))
            except (TypeError, ValueError):
                pass
        if "items" in updates and isinstance(updates["items"], list):
            cleaned = []
            for i, it in enumerate(updates["items"]):
                if not isinstance(it, dict):
                    continue
                mid = str(it.get("media_id") or "").strip()
                if not mid:
                    continue
                cleaned.append({"media_id": mid, "order": i})
            p["items"] = cleaned
        found = p
        break
    if not found:
        raise KeyError("Playlist introuvable")
    save_playlists(data)
    return found


def set_active_playlist(playlist_id: str) -> dict[str, Any]:
    data = load_playlists()
    ids = {p.get("id") for p in (data.get("playlists") or []) if isinstance(p, dict)}
    if playlist_id not in ids:
        raise KeyError("Playlist introuvable")
    data["active_playlist_id"] = playlist_id
    save_playlists(data)
    return get_active_playlist()


def create_playlist(name: str) -> dict[str, Any]:
    data = load_playlists()
    pl = {
        "id": _new_id("pl"),
        "name": (name or "Playlist").strip() or "Playlist",
        "loop": True,
        "play_mode": "sequential",
        "random_avoid_recent": 5,
        "items": [],
    }
    playlists = list(data.get("playlists") or [])
    playlists.append(pl)
    data["playlists"] = playlists
    save_playlists(data)
    return pl


# —— Jingle schedule ——


def _default_jingle_schedule() -> dict[str, Any]:
    return {
        "version": 1,
        "between_tracks": {
            "enabled": False,
            "every_n_songs": 3,
            "jingle_ids": [],
            "pick": "random",
        },
        "clock": [],
        "favorites": [],
        "duck_db": -12,
    }


def load_jingle_schedule() -> dict[str, Any]:
    data = _read_json(JINGLE_SCHEDULE_FILE)
    if not data:
        data = _default_jingle_schedule()
        save_jingle_schedule(data)
        return data
    data.setdefault("between_tracks", _default_jingle_schedule()["between_tracks"])
    data.setdefault("clock", [])
    data.setdefault("favorites", [])
    data.setdefault("duck_db", -12)
    bt = data["between_tracks"]
    if not isinstance(bt, dict):
        data["between_tracks"] = _default_jingle_schedule()["between_tracks"]
    else:
        if bt.get("pick") not in ("sequential", "random"):
            bt["pick"] = "random"
        if not isinstance(bt.get("jingle_ids"), list):
            bt["jingle_ids"] = []
        try:
            bt["every_n_songs"] = max(1, int(bt.get("every_n_songs") or 3))
        except (TypeError, ValueError):
            bt["every_n_songs"] = 3
        bt["enabled"] = bool(bt.get("enabled"))
    data["version"] = 1
    return data


def save_jingle_schedule(data: dict[str, Any]) -> None:
    data["version"] = 1
    _write_json(JINGLE_SCHEDULE_FILE, data)


def update_jingle_schedule(updates: dict[str, Any]) -> dict[str, Any]:
    data = load_jingle_schedule()
    if "between_tracks" in updates and isinstance(updates["between_tracks"], dict):
        bt = dict(data.get("between_tracks") or {})
        src = updates["between_tracks"]
        if "enabled" in src:
            bt["enabled"] = bool(src["enabled"])
        if "every_n_songs" in src:
            try:
                bt["every_n_songs"] = max(1, int(src["every_n_songs"]))
            except (TypeError, ValueError):
                pass
        if "jingle_ids" in src and isinstance(src["jingle_ids"], list):
            bt["jingle_ids"] = [str(x) for x in src["jingle_ids"] if str(x).strip()]
        if "pick" in src:
            pick = str(src["pick"] or "random")
            bt["pick"] = pick if pick in ("sequential", "random") else "random"
        data["between_tracks"] = bt
    if "clock" in updates and isinstance(updates["clock"], list):
        clock = []
        for entry in updates["clock"]:
            if not isinstance(entry, dict):
                continue
            t = str(entry.get("time") or "").strip()
            if not re.match(r"^\d{1,2}:\d{2}$", t):
                continue
            hh, mm = t.split(":")
            t = f"{int(hh):02d}:{int(mm):02d}"
            pick = str(entry.get("pick") or "sequential")
            if pick not in ("sequential", "random"):
                pick = "sequential"
            days = entry.get("days")
            if not isinstance(days, list):
                days = [1, 2, 3, 4, 5, 6, 7]
            days = [int(d) for d in days if str(d).isdigit() and 1 <= int(d) <= 7]
            ids = [str(x) for x in (entry.get("jingle_ids") or []) if str(x).strip()]
            clock.append({"time": t, "jingle_ids": ids, "pick": pick, "days": days or [1, 2, 3, 4, 5, 6, 7]})
        data["clock"] = clock
    if "favorites" in updates and isinstance(updates["favorites"], list):
        data["favorites"] = [str(x) for x in updates["favorites"] if str(x).strip()]
    if "duck_db" in updates:
        try:
            data["duck_db"] = int(updates["duck_db"])
        except (TypeError, ValueError):
            pass
    save_jingle_schedule(data)
    return data
