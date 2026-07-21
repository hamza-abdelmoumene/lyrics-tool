"""Pluggable now-playing backends and the auto-selector.

``lyricsooo`` reads the active player through whichever :class:`PlayerBackend`
fits the host OS. Selection is automatic — the first backend whose cheap
:meth:`~base.PlayerBackend.available` probe passes wins — but can be overridden
with ``--player-backend`` / ``$LYRICSOOO_PLAYER_BACKEND`` for testing or unusual
setups.
"""
from __future__ import annotations

import os
from typing import List, Optional, Type

from .base import NowPlaying, NullBackend, PlayerBackend, is_ad
from .macos import MacNowPlayingBackend
from .playerctl import PlayerctlBackend
from .windows import WindowsMediaBackend

__all__ = [
    "NowPlaying", "PlayerBackend", "is_ad",
    "select_backend", "backend_names",
    "PlayerctlBackend", "WindowsMediaBackend", "MacNowPlayingBackend", "NullBackend",
]

# Preference order for auto-detection. Each backend's ``available()`` is
# OS-guarded, so at most one matches on a given machine.
_BACKENDS: tuple = (PlayerctlBackend, WindowsMediaBackend, MacNowPlayingBackend)

# Friendly names/aliases accepted by --player-backend / the env override.
_ALIASES = {
    "playerctl": PlayerctlBackend, "mpris": PlayerctlBackend, "linux": PlayerctlBackend,
    "smtc": WindowsMediaBackend, "windows": WindowsMediaBackend, "win": WindowsMediaBackend,
    "nowplaying-cli": MacNowPlayingBackend, "macos": MacNowPlayingBackend,
    "mac": MacNowPlayingBackend, "darwin": MacNowPlayingBackend,
    "none": NullBackend, "null": NullBackend,
}


def backend_names() -> List[str]:
    """Canonical backend names, for help text and diagnostics."""
    return [b.name for b in _BACKENDS]


def select_backend(prefer: Optional[str] = None) -> PlayerBackend:
    """Return the backend to use.

    ``prefer`` (or ``$LYRICSOOO_PLAYER_BACKEND``) forces a named backend even if
    its availability probe is unsure — an explicit override is respected. With
    no preference, the first backend that reports itself available wins; if none
    do (native Windows/macOS without the helper), a :class:`NullBackend` keeps
    the visualizer alive on its idle screen.
    """
    prefer = prefer or os.environ.get("LYRICSOOO_PLAYER_BACKEND")
    if prefer:
        cls: Optional[Type[PlayerBackend]] = _ALIASES.get(prefer.strip().lower())
        if cls is not None:
            return cls()

    for cls in _BACKENDS:
        try:
            if cls.available():
                return cls()
        except Exception:
            continue
    return NullBackend()
