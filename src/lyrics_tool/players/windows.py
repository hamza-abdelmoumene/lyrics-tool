"""Windows backend: the System Media Transport Controls (SMTC).

Reads whatever is playing through Windows' global media session — Spotify, the
Groove/Media Player, browsers, etc. — via the ``winsdk`` projection of
``Windows.Media.Control``. That package is an opt-in extra (``pip install
'lyrics-tool[windows]'``); without it this backend simply reports itself
unavailable and the visualizer falls back to its idle screen.

All Windows-only imports live *inside* the methods, so importing this module on
Linux/macOS is always safe (it just never reports itself available there).
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from typing import Optional

from .base import NowPlaying, PlayerBackend

# Windows.Media.Control.GlobalSystemMediaTransportControlsSessionPlaybackStatus
_PLAYING = 4
_PAUSED = 5


def _run_async(coro):
    """Run one winsdk coroutine to completion on a private event loop."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _status_name(code: int) -> str:
    return {_PLAYING: "Playing", _PAUSED: "Paused"}.get(code, "Stopped")


def _build_snapshot(status_code, timeline, props, sampled_at, now=None):
    """Assemble a :class:`NowPlaying` from already-fetched SMTC objects.

    Kept free of any winsdk calls so it's unit-testable with plain fakes: pass a
    ``timeline`` exposing ``position`` / ``last_updated_time`` / ``start_time`` /
    ``end_time`` and ``props`` exposing ``title`` / ``artist`` / ``album_title``.
    ``now`` is injectable for deterministic position-extrapolation tests.
    """
    status = _status_name(int(status_code))

    # SMTC gives the position as of ``last_updated_time``; extrapolate with the
    # wall clock while playing so the sync loop tracks in real time.
    try:
        position = timeline.position.total_seconds()
        last = getattr(timeline, "last_updated_time", None)
        if status == "Playing" and last is not None:
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            ref = now or datetime.now(timezone.utc)
            elapsed = (ref - last).total_seconds()
            if 0 <= elapsed < 5:  # ignore absurd gaps from a stale session
                position += elapsed
    except Exception:
        position = 0.0

    try:
        duration = (timeline.end_time - timeline.start_time).total_seconds() or None
    except Exception:
        duration = None

    title = (getattr(props, "title", "") or "").strip()
    artist = (getattr(props, "artist", "") or "").strip()
    album = (getattr(props, "album_title", "") or "").strip() or None
    if not title:
        return None

    return NowPlaying(
        status=status,
        position=max(0.0, position),
        artist=artist,
        title=title,
        album=album,
        duration=duration if (duration and duration > 0) else None,
        trackid=None,  # SMTC has no stable per-track id; is_ad's title backup covers ads
        sampled_at=sampled_at,
    )


class WindowsMediaBackend(PlayerBackend):
    name = "smtc"

    def __init__(self) -> None:
        # SMTC exposes an app-user-model id per session; a substring pins one.
        self._player: Optional[str] = None

    @classmethod
    def available(cls) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import winsdk.windows.media.control  # noqa: F401
        except Exception:
            return False
        return True

    def set_player(self, name: Optional[str]) -> None:
        self._player = (name or "").strip().lower() or None

    # set_ignored is a no-op: SMTC already reports a single "current" session,
    # so there's no browser-hijack problem to guard against here.

    def _current_session(self, manager):
        """Pick the session to read — the pinned app if named, else current."""
        if self._player:
            try:
                for s in manager.get_sessions():
                    if self._player in (s.source_app_user_model_id or "").lower():
                        return s
            except Exception:
                pass
        return manager.get_current_session()

    def snapshot(self) -> Optional[NowPlaying]:
        try:
            from winsdk.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as Manager,
            )
        except Exception:
            return None

        try:
            t0 = time.monotonic()
            manager = _run_async(Manager.request_async())
            session = self._current_session(manager)
            if session is None:
                return None

            playback = session.get_playback_info()
            status_code = int(playback.playback_status)
            timeline = session.get_timeline_properties()
            props = _run_async(session.try_get_media_properties_async())
            t1 = time.monotonic()
        except Exception:
            return None

        return _build_snapshot(status_code, timeline, props, (t0 + t1) / 2)
