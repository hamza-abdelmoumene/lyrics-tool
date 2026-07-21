"""macOS backend: the now-playing info via the ``nowplaying-cli`` helper.

macOS has no MPRIS, and the underlying *MediaRemote* framework is private, so
this backend shells out to the community ``nowplaying-cli`` tool
(``brew install nowplaying-cli``). Without it installed the backend reports
itself unavailable and the offline tools still work.

Note: on macOS 15.4+ Apple further restricted MediaRemote, so live data may be
limited depending on the OS version and the player. Pin a theme colour source
(``--color-source caelestia`` / ``pywal`` / ``fixed:#…``) since no art URL is
exposed here.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from typing import List, Optional

from .base import NowPlaying, PlayerBackend

# Queried in one call; each value comes back on its own line ("null" if absent).
_KEYS = ["title", "artist", "album", "duration", "elapsedTime", "playbackRate"]


def _num(value: str) -> Optional[float]:
    value = value.strip()
    if not value or value.lower() == "null":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse(lines: List[str], sampled_at: float) -> Optional[NowPlaying]:
    """Turn ``nowplaying-cli get <_KEYS>`` output into a :class:`NowPlaying`.

    Kept pure (no subprocess) so it's unit-testable without macOS.
    """
    if len(lines) < len(_KEYS):
        return None

    def clean(v: str) -> str:
        v = v.strip()
        return "" if v.lower() == "null" else v

    title = clean(lines[0])
    artist = clean(lines[1])
    album = clean(lines[2]) or None
    duration = _num(lines[3])
    elapsed = _num(lines[4])
    rate = _num(lines[5])
    if not title:
        return None

    return NowPlaying(
        status="Playing" if (rate is None or rate > 0.5) else "Paused",
        position=elapsed if elapsed is not None else 0.0,
        artist=artist,
        title=title,
        album=album,
        duration=duration if (duration and duration > 0) else None,
        trackid=None,  # no stable id; is_ad's title backup covers Spotify ads
        sampled_at=sampled_at,
    )


class MacNowPlayingBackend(PlayerBackend):
    name = "nowplaying-cli"

    @classmethod
    def available(cls) -> bool:
        return sys.platform == "darwin" and shutil.which("nowplaying-cli") is not None

    # set_player / set_ignored: nowplaying-cli only reports the OS "now playing"
    # session, so there's nothing to pin or ignore — both stay no-ops.

    def snapshot(self) -> Optional[NowPlaying]:
        try:
            t0 = time.monotonic()
            result = subprocess.run(
                ["nowplaying-cli", "get", *_KEYS],
                capture_output=True, text=True, timeout=0.5,
            )
            t1 = time.monotonic()
        except Exception:
            return None
        if result.returncode != 0:
            return None
        return _parse(result.stdout.splitlines(), (t0 + t1) / 2)
