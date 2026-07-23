"""Linux / BSD backend: MPRIS over D-Bus via the ``playerctl`` CLI.

This is the reference backend and the only one with full art + local-file
support. It talks to Spotify and every MPRIS-capable local player (mpv, VLC,
rhythmbox, …) out of the box.

Auto-detect is deliberate about *which* player it follows. ``playerctl`` on its
own picks the first player by name order and ignores play state entirely — so a
*Stopped* Telegram voice message or a *Paused* YouTube tab would happily hijack
the lyrics from the Spotify track you're actually playing. Instead this backend
enumerates the players itself, drops the ones that never carry music (browsers,
chat/telephony apps), and prefers whatever is genuinely *Playing*.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from .base import NowPlaying, PlayerBackend

# Auto-detect skips these by default. Browsers publish an MPRIS player for
# *every* <video> — a YouTube lecture, a course, a background tab; chat /
# telephony / meeting apps publish one for a *voice message* or a call. Neither
# is the music you want lyrics for, and both would yank the panel away from
# Spotify / your player. Matched case-insensitively on the player's *base* name
# (see :func:`_base`), so the exact casing an app registers under —
# "TelegramDesktop", "Firefox" — never matters. Pass '' to follow anything.
DEFAULT_IGNORED_PLAYERS = (
    # web browsers — one MPRIS player per <video>
    "firefox,zen,librewolf,floorp,waterfox,mozilla,"
    "chromium,chrome,google-chrome,brave,vivaldi,opera,"
    "microsoft-edge,epiphany,qutebrowser,"
    # chat / telephony / meetings — voice notes & calls, never music
    "telegramdesktop,telegram,discord,webcord,vesktop,armcord,legcord,"
    "signal,signal-desktop,element,slack,skypeforlinux,skype,"
    "teams,teams-for-linux,whatsie,whatsapp,zoom,mumble,zulip"
)

# Tie-break among equally-playing candidates: a real music app should beat some
# random MPRIS source. Anything not listed still qualifies — it just sorts last.
_MUSIC_PRIORITY = (
    "spotify", "spotifyd", "ncspot", "spot", "mpd", "mopidy", "mpv", "vlc",
    "audacious", "rhythmbox", "clementine", "strawberry", "elisa", "lollypop",
    "amberol", "cmus", "musikcube", "deadbeef", "tauon",
    "youtube-music", "tidal-hifi", "cider", "feishin", "supersonic",
)

# status → sort rank: a Playing source always outranks a Paused one, which
# outranks Stopped/unknown. This is the whole point of resolving ourselves —
# playerctl's own auto-detect would pick by name order regardless of state.
_STATUS_RANK = {"Playing": 0, "Paused": 1, "Stopped": 2}

# The active player rarely changes, but the monitor thread polls ~8×/s. Cache
# the resolved choice for this long so we don't spawn a burst of playerctl
# processes on every poll; a player switch is still picked up within a beat.
_RESOLVE_TTL = 1.0

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


def _base(player: str) -> str:
    """Instance name → comparable base: ``firefox.instance_1_57`` → ``firefox``.

    Lower-cased so our own ignore/priority matching is case-insensitive, unlike
    playerctl's ``--ignore-player`` (which only matches the exact registered
    casing, e.g. ``TelegramDesktop``).
    """
    return player.split(".", 1)[0].lower()


class PlayerctlBackend(PlayerBackend):
    name = "playerctl"

    def __init__(self) -> None:
        # ``None`` player = auto-detect the active player.
        self._player: Optional[str] = None
        self._ignored: str = DEFAULT_IGNORED_PLAYERS
        # Cached auto-detect result (instance name or None) + when it was taken.
        self._resolved: Optional[str] = None
        self._resolved_at: float = 0.0

    @classmethod
    def available(cls) -> bool:
        return shutil.which("playerctl") is not None

    def set_player(self, name: Optional[str]) -> None:
        self._player = name or None
        self._resolved = None  # drop any cached auto choice

    def set_ignored(self, names: Optional[str]) -> None:
        # ``None`` keeps the default block-list; '' disables ignoring entirely.
        self._ignored = DEFAULT_IGNORED_PLAYERS if names is None else names
        self._resolved = None

    # ── player selection ─────────────────────────────────────────────────────
    def _ignored_set(self) -> set:
        return {p.strip().lower() for p in self._ignored.split(",") if p.strip()}

    def _list_players(self) -> List[str]:
        """Instance names of every running MPRIS player, or [] on any failure."""
        try:
            r = subprocess.run(["playerctl", "-l"], capture_output=True,
                               text=True, timeout=0.5)
        except Exception:
            return []
        if r.returncode != 0:
            return []
        return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]

    def _status_of(self, player: str) -> str:
        """'Playing' | 'Paused' | 'Stopped' for one player (Stopped on error)."""
        try:
            r = subprocess.run(["playerctl", "-p", player, "status"],
                               capture_output=True, text=True, timeout=0.5)
            if r.returncode == 0:
                return r.stdout.strip() or "Stopped"
        except Exception:
            pass
        return "Stopped"

    def _resolve_player(self) -> Optional[str]:
        """Pick the instance to follow, cached for :data:`_RESOLVE_TTL` seconds.

        Drops ignored players (browsers, chat apps), then prefers a *Playing*
        source, breaking ties toward known music apps. Returns ``None`` when
        nothing worth following is running, so the visualizer shows its idle
        screen instead of reading a random player's metadata.
        """
        now = time.monotonic()
        if self._resolved is not None and (now - self._resolved_at) < _RESOLVE_TTL:
            return self._resolved

        ignored = self._ignored_set()
        candidates = [p for p in self._list_players() if _base(p) not in ignored]

        chosen: Optional[str]
        if not candidates:
            chosen = None
        elif len(candidates) == 1:
            # Only one music-capable player — follow it whatever its state, no
            # need to spend a status probe.
            chosen = candidates[0]
        else:
            def score(item):
                idx, player = item
                base = _base(player)
                music = _MUSIC_PRIORITY.index(base) if base in _MUSIC_PRIORITY \
                    else len(_MUSIC_PRIORITY)
                return (_STATUS_RANK.get(self._status_of(player), 2), music, idx)

            chosen = min(enumerate(candidates), key=score)[1]

        self._resolved = chosen
        self._resolved_at = now
        return chosen

    def _run_playerctl(self, args: List[str]) -> Optional[subprocess.CompletedProcess]:
        """Run playerctl against the pinned/auto-resolved player.

        Returns ``None`` when auto-detect finds nothing to follow, so callers
        degrade to the idle screen rather than reading whatever player happens
        to sort first.
        """
        player: Optional[str]
        if self._player:
            player = self._player  # an explicit pin wins outright.
        else:
            player = self._resolve_player()
            if player is None:
                return None
        try:
            return subprocess.run(
                ["playerctl", "--player", player, *args],
                capture_output=True, text=True, timeout=0.5,
            )
        except Exception:
            return None

    def snapshot(self) -> Optional[NowPlaying]:
        t0 = time.monotonic()
        result = self._run_playerctl(["metadata", "--format", _STATE_FORMAT])
        t1 = time.monotonic()

        if result is None or result.returncode != 0:
            # The followed player may have just vanished/stopped; re-resolve on
            # the next poll instead of clinging to a dead choice.
            self._resolved = None
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
        result = self._run_playerctl(["metadata", "--format", "{{mpris:artUrl}}"])
        if result is not None and result.returncode == 0:
            return result.stdout.strip() or None
        return None

    def audio_file(self) -> Optional[Path]:
        """Local file backing the track, from ``xesam:url`` (``file://…``)."""
        result = self._run_playerctl(["metadata", "--format", "{{xesam:url}}"])
        if result is not None and result.returncode == 0:
            url = result.stdout.strip()
            if url.startswith("file://"):
                return Path(url[7:])
        return None
