# -*- coding: utf-8 -*-
"""Moteur antenne : playlists, jingles, encodeur Icecast/Shoutcast (ffmpeg).

V1 hybride (plan) : fichiers locaux → ffmpeg → Icecast/Shoutcast.
Les reporters WebRTC restent hors de ce bus.
"""
from __future__ import annotations

import random
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from auth_session import APP_DIR
from radio_store import (
    get_active_playlist,
    get_media,
    load_jingle_schedule,
    load_stream_config,
    resolve_media_path,
)


def find_ffmpeg(configured: str = "") -> str | None:
    if configured:
        p = Path(configured).expanduser()
        if p.is_file():
            return str(p)
    which = shutil.which("ffmpeg")
    if which:
        return which
    # Emplacements Windows fréquents
    for candidate in (
        APP_DIR / "ffmpeg" / "ffmpeg.exe",
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def build_icecast_url(cfg: dict[str, Any]) -> str:
    user = quote(str(cfg.get("username") or "source"), safe="")
    password = quote(str(cfg.get("password") or ""), safe="")
    host = str(cfg.get("host") or "").strip()
    port = int(cfg.get("port") or 8000)
    mount = str(cfg.get("mount") or "/stream").strip() or "/stream"
    if not mount.startswith("/"):
        mount = "/" + mount
    # ffmpeg utilise le protocole icecast:// même pour beaucoup de Shoutcast
    return f"icecast://{user}:{password}@{host}:{port}{mount}"


def test_stream_endpoint(cfg: dict[str, Any], timeout: float = 4.0) -> dict[str, Any]:
    host = str(cfg.get("host") or "").strip()
    port = int(cfg.get("port") or 0)
    if not host or not port:
        return {"ok": False, "error": "Host et port requis"}
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as e:
        return {"ok": False, "error": f"Impossible de joindre {host}:{port} — {e}"}
    ffmpeg = find_ffmpeg(str(cfg.get("ffmpeg_path") or ""))
    if not ffmpeg:
        return {
            "ok": True,
            "tcp_ok": True,
            "ffmpeg": False,
            "warning": "TCP OK, mais ffmpeg introuvable (installez ffmpeg ou indiquez le chemin).",
        }
    return {"ok": True, "tcp_ok": True, "ffmpeg": True, "ffmpeg_path": ffmpeg}


class RadioEngine:
    """Singleton logique antenne (thread-safe)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._playing = False
        self._streaming = False
        self._paused = False
        self._proc: subprocess.Popen[Any] | None = None
        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._skip_event = threading.Event()
        self._fire_jingle_id: str | None = None
        self._current: dict[str, Any] | None = None
        self._next: dict[str, Any] | None = None
        self._current_kind = "song"  # song | jingle
        self._songs_since_jingle = 0
        self._recent_song_ids: list[str] = []
        self._shuffle_order: list[str] = []
        self._shuffle_pos = 0
        self._seq_index = 0
        self._jingle_seq_pos = 0
        self._clock_seq: dict[str, int] = {}
        self._last_jingle_id: str | None = None
        self._fired_clock_keys: set[str] = set()
        self._error = ""
        self._started_at = 0.0
        self._track_started_at = 0.0
        self._clock_thread: threading.Thread | None = None
        self._ensure_clock_thread()

    def _ensure_clock_thread(self) -> None:
        if self._clock_thread and self._clock_thread.is_alive():
            return
        self._clock_thread = threading.Thread(target=self._clock_loop, name="radio-clock", daemon=True)
        self._clock_thread.start()

    def _clock_loop(self) -> None:
        while True:
            try:
                self._check_clock_jingles()
            except Exception:
                pass
            time.sleep(15)

    def _check_clock_jingles(self) -> None:
        with self._lock:
            if not self._playing:
                return
            sched = load_jingle_schedule()
            now = datetime.now()
            # weekday: Monday=0 → plan days 1=Mon … 7=Sun
            day = now.isoweekday()
            key = now.strftime("%Y-%m-%d %H:%M")
            hm = now.strftime("%H:%M")
            for entry in sched.get("clock") or []:
                if not isinstance(entry, dict):
                    continue
                if entry.get("time") != hm:
                    continue
                days = entry.get("days") or [1, 2, 3, 4, 5, 6, 7]
                if day not in days:
                    continue
                stamp = f"{key}|{entry.get('time')}"
                if stamp in self._fired_clock_keys:
                    continue
                self._fired_clock_keys.add(stamp)
                # Nettoyage vieux clés
                if len(self._fired_clock_keys) > 200:
                    self._fired_clock_keys = {stamp}
                jid = self._pick_from_pool(
                    list(entry.get("jingle_ids") or []),
                    str(entry.get("pick") or "sequential"),
                    clock_key=str(entry.get("time") or ""),
                )
                if jid:
                    self._fire_jingle_id = jid
                    self._skip_event.set()
                    break

    def status(self) -> dict[str, Any]:
        with self._lock:
            cfg = load_stream_config()
            ffmpeg = find_ffmpeg(str(cfg.get("ffmpeg_path") or ""))
            cur = dict(self._current) if self._current else None
            nxt = dict(self._next) if self._next else None
            elapsed = 0.0
            if self._playing and not self._paused and self._track_started_at:
                elapsed = max(0.0, time.time() - self._track_started_at)
            return {
                "ok": True,
                "playing": self._playing,
                "paused": self._paused,
                "streaming": self._streaming,
                "current": cur,
                "next": nxt,
                "current_kind": self._current_kind,
                "songs_since_jingle": self._songs_since_jingle,
                "error": self._error,
                "ffmpeg_found": bool(ffmpeg),
                "ffmpeg_path": ffmpeg or "",
                "elapsed_s": round(elapsed, 1),
                "play_mode": (get_active_playlist() or {}).get("play_mode") or "sequential",
            }

    def _playlist_song_ids(self) -> list[str]:
        pl = get_active_playlist()
        ids: list[str] = []
        for it in pl.get("items") or []:
            if not isinstance(it, dict):
                continue
            mid = str(it.get("media_id") or "").strip()
            if not mid:
                continue
            media = get_media(mid)
            if media and media.get("kind") == "song" and resolve_media_path(media):
                ids.append(mid)
        return ids

    def _media_payload(self, media_id: str, *, kind_override: str | None = None) -> dict[str, Any] | None:
        media = get_media(media_id)
        if not media:
            return None
        path = resolve_media_path(media)
        if not path:
            return None
        return {
            "id": media["id"],
            "title": media.get("title") or media["id"],
            "kind": kind_override or media.get("kind") or "song",
            "path": media.get("path"),
            "abs_path": str(path),
        }

    def _pick_from_pool(self, ids: list[str], pick: str, *, clock_key: str = "") -> str | None:
        valid = []
        for mid in ids:
            m = get_media(mid)
            if m and resolve_media_path(m):
                valid.append(mid)
        if not valid:
            return None
        if pick == "random":
            choices = [x for x in valid if x != self._last_jingle_id] or valid
            return random.choice(choices)
        # sequential
        key = clock_key or "__between__"
        pos = self._clock_seq.get(key, 0) if clock_key else self._jingle_seq_pos
        mid = valid[pos % len(valid)]
        if clock_key:
            self._clock_seq[key] = pos + 1
        else:
            self._jingle_seq_pos = pos + 1
        return mid

    def _choose_next_song(self) -> dict[str, Any] | None:
        ids = self._playlist_song_ids()
        if not ids:
            return None
        pl = get_active_playlist()
        mode = pl.get("play_mode") or "sequential"
        avoid = int(pl.get("random_avoid_recent") or 5)
        avoid = min(avoid, max(0, len(ids) - 1))

        if mode == "random":
            candidates = [i for i in ids if i not in self._recent_song_ids[-avoid:]] or list(ids)
            mid = random.choice(candidates)
        elif mode == "shuffle_cycle":
            if not self._shuffle_order or set(self._shuffle_order) != set(ids):
                self._shuffle_order = list(ids)
                random.shuffle(self._shuffle_order)
                self._shuffle_pos = 0
            if self._shuffle_pos >= len(self._shuffle_order):
                random.shuffle(self._shuffle_order)
                self._shuffle_pos = 0
            mid = self._shuffle_order[self._shuffle_pos]
            self._shuffle_pos += 1
        else:
            if self._seq_index >= len(ids):
                if not pl.get("loop", True):
                    return None
                self._seq_index = 0
            mid = ids[self._seq_index % len(ids)]
            self._seq_index += 1

        return self._media_payload(mid, kind_override="song")

    def _maybe_jingle_after_song(self) -> dict[str, Any] | None:
        sched = load_jingle_schedule()
        bt = sched.get("between_tracks") or {}
        if not bt.get("enabled"):
            return None
        every_n = max(1, int(bt.get("every_n_songs") or 3))
        if self._songs_since_jingle < every_n:
            return None
        jid = self._pick_from_pool(list(bt.get("jingle_ids") or []), str(bt.get("pick") or "random"))
        if not jid:
            return None
        payload = self._media_payload(jid, kind_override="jingle")
        if payload:
            self._songs_since_jingle = 0
            self._last_jingle_id = jid
        return payload

    def _peek_next(self) -> dict[str, Any] | None:
        """Calcule un aperçu « À suivre » sans avancer les compteurs de façon durable.

        Pour sequential/shuffle on lit l'état ; pour random on tire un candidat
        informatif (peut différer du tirage réel au moment du play).
        """
        if self._fire_jingle_id:
            return self._media_payload(self._fire_jingle_id, kind_override="jingle")
        # Si on vient de finir assez de chansons, jingle possible
        sched = load_jingle_schedule()
        bt = sched.get("between_tracks") or {}
        if (
            self._current_kind == "song"
            and bt.get("enabled")
            and self._songs_since_jingle + (1 if self._playing and self._current_kind == "song" else 0)
            >= max(1, int(bt.get("every_n_songs") or 3))
        ):
            ids = list(bt.get("jingle_ids") or [])
            if ids:
                # Aperçu sans avancer : premier valide / ou autre que last
                for mid in ids:
                    if mid != self._last_jingle_id:
                        p = self._media_payload(mid, kind_override="jingle")
                        if p:
                            return p
                p = self._media_payload(ids[0], kind_override="jingle")
                if p:
                    return p
        ids = self._playlist_song_ids()
        if not ids:
            return None
        pl = get_active_playlist()
        mode = pl.get("play_mode") or "sequential"
        if mode == "sequential":
            idx = self._seq_index % len(ids) if ids else 0
            return self._media_payload(ids[idx], kind_override="song")
        if mode == "shuffle_cycle" and self._shuffle_order:
            pos = self._shuffle_pos % len(self._shuffle_order)
            return self._media_payload(self._shuffle_order[pos], kind_override="song")
        # random : montrer un candidat hors récents
        avoid = min(int(pl.get("random_avoid_recent") or 5), max(0, len(ids) - 1))
        candidates = [i for i in ids if i not in self._recent_song_ids[-avoid:]] or ids
        cur_id = (self._current or {}).get("id")
        candidates = [i for i in candidates if i != cur_id] or candidates
        return self._media_payload(candidates[0], kind_override="song")

    def _stop_proc(self) -> None:
        proc = self._proc
        self._proc = None
        if not proc:
            return
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _build_ffmpeg_cmd(self, abs_path: str, *, stream: bool) -> list[str] | None:
        cfg = load_stream_config()
        ffmpeg = find_ffmpeg(str(cfg.get("ffmpeg_path") or ""))
        if not ffmpeg:
            self._error = "ffmpeg introuvable. Installez-le ou renseignez le chemin dans Diffusion."
            return None
        bitrate = int(cfg.get("bitrate_kbps") or 128)
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-re",
            "-i",
            abs_path,
            "-vn",
            "-acodec",
            "libmp3lame",
            "-ab",
            f"{bitrate}k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-content_type",
            "audio/mpeg",
        ]
        if stream:
            if not cfg.get("password"):
                self._error = "Mot de passe SOURCE manquant dans la config diffusion."
                return None
            if not cfg.get("host"):
                self._error = "Host diffusion manquant."
                return None
            url = build_icecast_url(cfg)
            cmd += ["-f", "icecast", url]
        else:
            # Lecture locale « dry » : encoder vers null (avance le temps réel)
            # Sous Windows/Linux : null / NUL
            null_sink = "NUL" if Path("C:/").exists() else "/dev/null"
            cmd += ["-f", "mp3", null_sink]
        return cmd

    def _play_file(self, item: dict[str, Any], *, stream: bool) -> int:
        abs_path = item.get("abs_path") or ""
        cmd = self._build_ffmpeg_cmd(abs_path, stream=stream)
        if not cmd:
            return 1
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )
        except Exception as e:
            self._error = f"Échec lancement ffmpeg : {e}"
            return 1
        assert self._proc is not None
        while True:
            if self._stop_event.is_set() or self._skip_event.is_set():
                self._stop_proc()
                return 0
            if self._paused:
                time.sleep(0.2)
                continue
            ret = self._proc.poll()
            if ret is not None:
                err = ""
                try:
                    if self._proc.stderr:
                        err = (self._proc.stderr.read() or b"").decode("utf-8", errors="replace")[:400]
                except Exception:
                    pass
                self._proc = None
                if ret != 0 and stream:
                    self._error = (err or f"ffmpeg a quitté avec le code {ret}").strip()
                return ret
            time.sleep(0.25)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                # Fire jingle prioritaire
                fire_id = self._fire_jingle_id
                self._fire_jingle_id = None
                item = None
                kind = "song"
                if fire_id:
                    item = self._media_payload(fire_id, kind_override="jingle")
                    kind = "jingle"
                    if item:
                        self._last_jingle_id = fire_id
                if not item and self._current_kind == "song" and self._songs_since_jingle > 0:
                    # Après une chanson terminée normalement, tenter jingle
                    pass
                if not item:
                    # Si la dernière piste était une chanson, évaluer jingle between
                    if self._current and self._current_kind == "song":
                        item = self._maybe_jingle_after_song()
                        if item:
                            kind = "jingle"
                    if not item:
                        item = self._choose_next_song()
                        kind = "song"
                if not item:
                    self._playing = False
                    self._current = None
                    self._next = None
                    self._error = self._error or "Playlist vide ou fichiers manquants."
                    break
                self._current = {
                    "id": item["id"],
                    "title": item["title"],
                    "kind": kind,
                    "path": item.get("path"),
                }
                self._current_kind = kind
                self._track_started_at = time.time()
                self._skip_event.clear()
                stream = self._streaming
                self._next = self._peek_next()

            # Lecture hors lock
            self._play_file(item, stream=stream)

            with self._lock:
                if self._stop_event.is_set():
                    break
                skipped = self._skip_event.is_set()
                self._skip_event.clear()
                if kind == "song" and not skipped:
                    self._songs_since_jingle += 1
                    self._recent_song_ids.append(item["id"])
                    if len(self._recent_song_ids) > 40:
                        self._recent_song_ids = self._recent_song_ids[-40:]
                elif kind == "song" and skipped and not self._fire_jingle_id:
                    # Skip manuel chanson : compte pour every_n
                    self._songs_since_jingle += 1
                    self._recent_song_ids.append(item["id"])
                self._next = self._peek_next()

        with self._lock:
            self._playing = False
            self._paused = False
            self._stop_proc()

    def play(self, *, stream: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._playing and self._paused:
                self._paused = False
                return self.status()
            if self._playing:
                return self.status()
            if stream:
                cfg = load_stream_config()
                check = test_stream_endpoint(cfg)
                if not check.get("ok"):
                    self._error = check.get("error") or "Test diffusion échoué"
                    return {**self.status(), "ok": False, "error": self._error}
                if not find_ffmpeg(str(cfg.get("ffmpeg_path") or "")):
                    self._error = "ffmpeg introuvable"
                    return {**self.status(), "ok": False, "error": self._error}
            self._stop_event.clear()
            self._skip_event.clear()
            self._error = ""
            self._playing = True
            self._paused = False
            self._streaming = bool(stream)
            self._started_at = time.time()
            self._songs_since_jingle = 0
            self._worker = threading.Thread(target=self._worker_loop, name="radio-worker", daemon=True)
            self._worker.start()
            return self.status()

    def pause(self) -> dict[str, Any]:
        with self._lock:
            if self._playing:
                self._paused = True
                # Arrêter le morceau en cours (reprise = skip vers même logique simplifiée)
                self._stop_proc()
            return self.status()

    def resume(self) -> dict[str, Any]:
        return self.play(stream=self._streaming)

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._stop_event.set()
            self._skip_event.set()
            self._stop_proc()
            self._playing = False
            self._paused = False
            self._streaming = False
            self._current = None
            self._next = None
        return self.status()

    def skip(self) -> dict[str, Any]:
        with self._lock:
            if not self._playing:
                return self.status()
            self._skip_event.set()
            self._stop_proc()
        return self.status()

    def start_stream(self) -> dict[str, Any]:
        with self._lock:
            was_playing = self._playing
            stream_wanted = True
        if was_playing:
            self.stop()
            time.sleep(0.3)
        return self.play(stream=stream_wanted)

    def stop_stream(self) -> dict[str, Any]:
        """Coupe la diffusion réseau mais peut laisser la lecture locale — V1 : stop total."""
        return self.stop()

    def fire_jingle(self, media_id: str) -> dict[str, Any]:
        mid = str(media_id or "").strip()
        media = get_media(mid)
        if not media or not resolve_media_path(media):
            return {"ok": False, "error": "Jingle introuvable"}
        with self._lock:
            self._fire_jingle_id = mid
            already = self._playing
            if already:
                self._skip_event.set()
                self._stop_proc()
        if not already:
            # play() laisse _fire_jingle_id intact → premier titre = jingle
            st = self.play(stream=self._streaming)
            return {**st, "ok": True, "fired": mid}
        return {**self.status(), "ok": True, "fired": mid}


ENGINE = RadioEngine()
