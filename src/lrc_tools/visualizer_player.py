"""
Media player integration using playerctl
Handles communication with media players via MPRIS
"""
import subprocess
import time
from collections import namedtuple
from pathlib import Path
from typing import Optional, Tuple


PLAYER_NAME = 'spotify'


# A single atomic snapshot of the player, read in one playerctl call.
# ``sampled_at`` is the monotonic-clock midpoint of that call, so the display
# loop can compensate for query latency and stay frame-accurate.
PlayerState = namedtuple(
    'PlayerState',
    ['status', 'position', 'artist', 'title', 'album', 'duration', 'sampled_at'],
)

_STATE_FORMAT = (
    '{{status}}|||{{position}}|||{{artist}}|||{{title}}|||'
    '{{album}}|||{{mpris:length}}'
)


def _run_playerctl(args: list) -> subprocess.CompletedProcess:
    """Run playerctl with preferred player target and timeout"""
    cmd = ['playerctl']
    if PLAYER_NAME:
        cmd.extend(['--player', PLAYER_NAME])
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=0.5)


def get_state() -> Optional[PlayerState]:
    """Read the player's full state in a single playerctl call.

    Collapsing status, position and metadata into one subprocess (instead of
    the three separate calls used before) cuts per-tick overhead ~3x and —
    crucially for clean track switches — samples the position and the title
    from the *same* MPRIS snapshot, so a song change can no longer race a stale
    position left over from the previous track.

    In ``metadata --format`` playerctl reports position/length in microseconds,
    so both are converted to seconds. Returns None when nothing is playing or
    the output can't be parsed.
    """
    try:
        t0 = time.monotonic()
        result = _run_playerctl(['metadata', '--format', _STATE_FORMAT])
        t1 = time.monotonic()
    except Exception:
        return None

    if result.returncode != 0:
        return None

    parts = result.stdout.strip().split('|||')
    if len(parts) != 6:
        return None

    status, pos_us, artist, title, album, length_us = parts

    def _to_seconds(value: str) -> Optional[float]:
        value = value.strip()
        if not value:
            return None
        try:
            return float(value) / 1_000_000
        except ValueError:
            return None

    position = _to_seconds(pos_us)
    if position is None or not title:
        return None

    return PlayerState(
        status=status or None,
        position=position,
        artist=artist,
        title=title,
        album=album or None,
        duration=_to_seconds(length_us),
        sampled_at=(t0 + t1) / 2,
    )


def get_position() -> Optional[float]:
    """
    Get current playback position in seconds.
    
    Returns:
        Current position in seconds, or None if unavailable
    """
    try:
        result = _run_playerctl(['position'])
        return float(result.stdout.strip()) if result.returncode == 0 else None
    except Exception:
        return None


def get_track() -> Optional[Tuple[str, str]]:
    """
    Get currently playing track information.
    
    Returns:
        Tuple of (artist, title), or None if unavailable
    """
    try:
        result = _run_playerctl(['metadata', '--format', '{{artist}}|||{{title}}'])
        if result.returncode == 0:
            parts = result.stdout.strip().split('|||')
            return (parts[0], parts[1]) if len(parts) == 2 else None
    except Exception:
        return None


def get_track_full() -> Optional[Tuple[str, str, Optional[str], Optional[float]]]:
    """
    Get rich track metadata in a single playerctl call.

    Returns:
        (artist, title, album, duration_seconds) or None. album/duration may be
        None when the player doesn't expose them. Used for exact LRCLIB lookups.
    """
    try:
        result = _run_playerctl(
            ['metadata', '--format', '{{artist}}|||{{title}}|||{{album}}|||{{mpris:length}}']
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split('|||')
            if len(parts) == 4:
                artist, title, album, length = parts
                duration = int(length) / 1_000_000 if length.isdigit() else None
                return (artist, title, album or None, duration)
    except Exception:
        return None
    return None


def get_status() -> Optional[str]:
    """
    Get current playback status.
    
    Returns:
        Status string ('Playing', 'Paused', 'Stopped'), or None if unavailable
    """
    try:
        result = _run_playerctl(['status'])
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def get_audio_file_info() -> Optional[Path]:
    """
    Get currently playing audio file path.
    
    Returns:
        Path to audio file, or None if unavailable
    """
    try:
        result = _run_playerctl(['metadata', '--format', '{{xesam:url}}'])
        if result.returncode == 0:
            url = result.stdout.strip()
            if url.startswith('file://'):
                return Path(url[7:])
    except Exception:
        pass
    return None


def is_paused() -> bool:
    """
    Check if playback is currently paused.
    
    Returns:
        True if paused, False otherwise
    """
    status = get_status()
    return status == 'Paused' if status else False


def is_playing() -> bool:
    """
    Check if playback is currently active.
    
    Returns:
        True if playing, False otherwise
    """
    status = get_status()
    return status == 'Playing' if status else False
