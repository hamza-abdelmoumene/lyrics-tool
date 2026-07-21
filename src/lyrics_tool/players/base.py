"""Shared types for the pluggable now-playing backends.

The visualizer only ever needs an *atomic snapshot* of what is playing right
now. Every platform exposes that differently — MPRIS on Linux, the System
Media Transport Controls on Windows, ``nowplaying-cli`` on macOS — so each is
wrapped in a small :class:`PlayerBackend` that returns the same
:class:`NowPlaying` record. The rest of the code never imports a platform API
directly; it talks to whichever backend :func:`lyrics_tool.players.select_backend`
picked.
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple, Optional, Tuple


class NowPlaying(NamedTuple):
    """One atomic snapshot of the active player.

    ``sampled_at`` is the monotonic-clock midpoint of the read, so the display
    loop can compensate for query latency and stay frame-accurate. Fields the
    player doesn't expose are ``None``. This is the single currency every
    backend deals in, whatever OS API it wraps underneath.
    """

    status: Optional[str]        # 'Playing' | 'Paused' | 'Stopped' | None
    position: Optional[float]    # seconds into the track
    artist: Optional[str]
    title: Optional[str]
    album: Optional[str]
    duration: Optional[float]    # track length in seconds
    trackid: Optional[str]       # opaque per-track id (used for ad detection)
    sampled_at: float            # time.monotonic() when this was read


def is_ad(state: Optional[NowPlaying]) -> bool:
    """True when the snapshot is a Spotify advertisement rather than a track.

    Spotify free tags an ad's ``trackid`` with an ``:ad:`` / ``/ad/`` segment;
    that's the reliable signal. A blank artist with a generic ad title is kept
    as a backup. Other players never match, so local playback is unaffected.
    """
    if state is None:
        return False
    tid = (state.trackid or "").lower()
    if ":ad:" in tid or "/ad/" in tid:
        return True
    return not state.artist and (state.title or "").lower() in ("advertisement", "spotify")


class PlayerBackend:
    """Base class for a now-playing source.

    Subclasses implement :meth:`snapshot` (and optionally :meth:`art_url` /
    :meth:`audio_file`) for one platform. Everything is best-effort: a method
    that can't answer returns ``None`` rather than raising, so the visualizer
    degrades to its idle screen instead of crashing. :meth:`available` is a
    cheap, side-effect-free probe used to auto-select a backend at startup.
    """

    #: Short identifier, e.g. ``"playerctl"``. Shown by ``--player-backend`` help.
    name: str = "none"

    @classmethod
    def available(cls) -> bool:
        """Whether this backend can run on the current machine (cheap probe)."""
        return False

    def set_player(self, name: Optional[str]) -> None:
        """Pin to a specific player by name (``None`` = auto-detect)."""

    def set_ignored(self, names: Optional[str]) -> None:
        """Set players auto-detect must skip (backend-specific; may be a no-op)."""

    def snapshot(self) -> Optional[NowPlaying]:
        """Read the current player state, or ``None`` when nothing is playing."""
        return None

    def art_url(self) -> Optional[str]:
        """URL/path to the current track's cover art, or ``None`` if unavailable."""
        return None

    def audio_file(self) -> Optional[Path]:
        """Local file backing the current track, or ``None`` for streamed audio."""
        return None

    def track_full(self) -> Optional[Tuple[str, str, Optional[str], Optional[float]]]:
        """``(artist, title, album, duration)`` for an exact LRCLIB lookup.

        Derived from :meth:`snapshot` so backends get it for free; a backend can
        override it if it has a cheaper path.
        """
        s = self.snapshot()
        if s is None or not s.title:
            return None
        return (s.artist or "", s.title, s.album, s.duration)


class NullBackend(PlayerBackend):
    """Fallback when no live-sync source exists on this platform.

    Used on native Windows/macOS without the optional helper installed: the
    offline ``lyricsooo-fetch`` / ``lyricsooo-cook`` tools still work, and the
    visualizer shows its calm idle screen instead of erroring out.
    """

    name = "none"

    @classmethod
    def available(cls) -> bool:
        return True
