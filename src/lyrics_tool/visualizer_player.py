"""Now-playing facade — one stable API over the per-OS player backends.

The visualizer only imports *this* module; it never touches an OS media API
directly. Underneath, :func:`lyrics_tool.players.select_backend` picks the right
:class:`~lyrics_tool.players.PlayerBackend` for the host (MPRIS/``playerctl`` on
Linux, SMTC on Windows, ``nowplaying-cli`` on macOS), so the same loop, sync
clock and tests work everywhere.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from .players import NowPlaying, backend_names, is_ad, select_backend

# Kept as an alias for backwards compatibility: existing code and tests
# construct/annotate ``PlayerState`` — it is exactly the cross-platform snapshot.
PlayerState = NowPlaying

__all__ = [
    "PlayerState", "is_ad", "backend_names", "backend_name", "set_backend",
    "set_player", "set_ignored", "get_state", "get_art_url",
    "get_audio_file_info", "get_track_full",
]

# The active backend, chosen once at import from the platform + environment.
_backend = select_backend()


def set_backend(name: Optional[str]) -> None:
    """Force a specific backend by name (see ``lyrics_tool.players.backend_names``)."""
    global _backend
    _backend = select_backend(name)


def backend_name() -> str:
    """Name of the backend currently in use (e.g. ``'playerctl'``, ``'smtc'``)."""
    return _backend.name


def set_player(name: Optional[str]) -> None:
    """Pin the visualizer to a specific player (``None`` = auto-detect)."""
    _backend.set_player(name)


def set_ignored(names: Optional[str]) -> None:
    """Set players auto-detect should skip (backend-specific; may be a no-op)."""
    _backend.set_ignored(names)


def get_state() -> Optional[PlayerState]:
    """One atomic snapshot of the active player, or ``None`` when nothing plays."""
    return _backend.snapshot()


def get_art_url() -> Optional[str]:
    """Cover-art URL/path for the current track, or ``None`` if unavailable."""
    return _backend.art_url()


def get_audio_file_info() -> Optional[Path]:
    """Local file backing the current track, or ``None`` for streamed audio."""
    return _backend.audio_file()


def get_track_full() -> Optional[Tuple[str, str, Optional[str], Optional[float]]]:
    """``(artist, title, album, duration)`` for an exact LRCLIB lookup, or ``None``."""
    return _backend.track_full()
