"""Linux / BSD backend: MPRIS over D-Bus via the ``playerctl`` CLI.

This is the reference backend and the only one with full art + local-file
support. It talks to Spotify and every MPRIS-capable local player (mpv, VLC,
rhythmbox, …) out of the box.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from .base import NowPlaying, PlayerBackend

# Players auto-follow ignores when no explicit player is pinned. Browsers
# publish an MPRIS player for *every* <video> — a YouTube lecture, a course, a
# background tab — and would yank the lyrics away from the music you're actually
# playing. Ignoring them by default means auto-detect quietly skips the browser
# and follows Spotify / a local player instead. Pass '' to follow anything.
DEFAULT_IGNORED_PLAYERS = (
    "firefox,zen,librewolf,floorp,waterfox,mozilla,"
    "chromium,chrome,google-chrome,brave,vivaldi,opera,"
    "microsoft-edge,epiphany,qutebrowser"
)

# One playerctl call reads status + position + metadata from a single MPRIS
# snapshot, so a track change can't race a stale position from the last song.
_STATE_FORMAT = (
    "{{status}}|||{{position}}|||{{artist}}|||{{title}}|||"
    "{{album}}|||{{mpris:length}}|||{{mpris:trackid}}"
)


def _us_to_seconds(value: str) -> Optional[float]:
    """playerctl reports position/length in microseconds; convert to seconds."""
    value = value.strip()
    if not value:
        return None
    try:
        return float(value) / 1_000_000
    except ValueError:
        return None


class PlayerctlBackend(PlayerBackend):
    name = "playerctl"

    def __init__(self) -> None:
        # ``None`` player = auto-detect the active player.
        self._player: Optional[str] = None
        self._ignored: str = DEFAULT_IGNORED_PLAYERS

    @classmethod
    def available(cls) -> bool:
        return shutil.which("playerctl") is not None

    def set_player(self, name: Optional[str]) -> None:
        self._player = name or None

    def set_ignored(self, names: Optional[str]) -> None:
        # ``None`` keeps the browser default; '' disables ignoring entirely.
        self._ignored = DEFAULT_IGNORED_PLAYERS if names is None else names

    def _run_playerctl(self, args: List[str]) -> subprocess.CompletedProcess:
        """Run playerctl targeting the pinned/auto player, with a hard timeout."""
        cmd = ["playerctl"]
        if self._player:
            # An explicit pin wins outright — the user asked for this player.
            cmd.extend(["--player", self._player])
        elif self._ignored:
            # Auto-detect, but never let a browser's <video> hijack the lyrics.
            cmd.extend(["--ignore-player", self._ignored])
        cmd.extend(args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=0.5)

    def snapshot(self) -> Optional[NowPlaying]:
        try:
            t0 = time.monotonic()
            result = self._run_playerctl(["metadata", "--format", _STATE_FORMAT])
            t1 = time.monotonic()
        except Exception:
            return None

        if result.returncode != 0:
            return None

        parts = result.stdout.strip().split("|||")
        if len(parts) != 7:
            return None

        status, pos_us, artist, title, album, length_us, trackid = parts
        position = _us_to_seconds(pos_us)
        # Ads have no usable title; let them through (title may be blank) so the
        # display loop can show the ad screen. Real tracks still need a title.
        tid = (trackid or "").lower()
        ad = ":ad:" in tid or "/ad/" in tid
        if position is None or (not title and not ad):
            return None

        return NowPlaying(
            status=status or None,
            position=position,
            artist=artist,
            title=title,
            album=album or None,
            duration=_us_to_seconds(length_us),
            trackid=trackid or None,
            sampled_at=(t0 + t1) / 2,
        )

    def art_url(self) -> Optional[str]:
        """Album-art URL the player exposes (Spotify: https://i.scdn.co/…)."""
        try:
            result = self._run_playerctl(["metadata", "--format", "{{mpris:artUrl}}"])
            if result.returncode == 0:
                return result.stdout.strip() or None
        except Exception:
            pass
        return None

    def audio_file(self) -> Optional[Path]:
        """Local file backing the track, from ``xesam:url`` (``file://…``)."""
        try:
            result = self._run_playerctl(["metadata", "--format", "{{xesam:url}}"])
            if result.returncode == 0:
                url = result.stdout.strip()
                if url.startswith("file://"):
                    return Path(url[7:])
        except Exception:
            pass
        return None
