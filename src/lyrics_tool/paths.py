"""Default filesystem locations for lyrics-tool.

All user data lives under ``$XDG_DATA_HOME/lyrics-tool`` (which defaults to
``~/.local/share/lyrics-tool``), so the three commands share a single, stable
layout and the visualizer "just works" with no flags:

    <data>/lyrics/raw        # lyricsooo-fetch downloads .lrc files here
    <data>/lyrics/processed  # lyricsooo-cook writes here; lyricsooo reads here

The visualizer also caches/fetches lyrics on the fly into ``processed`` (with a
sibling ``raw``) as tracks play, so these two directories are intentionally
siblings under ``lyrics/``.
"""
import os
from pathlib import Path

APP_NAME = "lyrics-tool"


def data_home() -> Path:
    """Base data directory, honouring ``$XDG_DATA_HOME`` when set."""
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / APP_NAME


def raw_dir() -> Path:
    """Where ``lyricsooo-fetch`` saves freshly downloaded ``.lrc`` files."""
    return data_home() / "lyrics" / "raw"


def processed_dir() -> Path:
    """Where ``lyricsooo-cook`` writes output and ``lyricsooo`` reads from."""
    return data_home() / "lyrics" / "processed"


def state_home() -> Path:
    """Base state directory, honouring ``$XDG_STATE_HOME`` when set.

    State is small, machine-local calibration the user tweaks at runtime — kept
    apart from the (portable, re-downloadable) lyric cache under ``data_home``.
    """
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / APP_NAME


def sync_offset_file() -> Path:
    """Where the visualizer persists the live-nudged sync offset (seconds).

    Written when you tap the ``+`` / ``-`` keys to slide lyrics earlier/later so
    the calibration survives across launches.
    """
    return state_home() / "sync_offset"


def ensure_dir(path: Path) -> Path:
    """Create ``path`` (and any missing parents) and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path
