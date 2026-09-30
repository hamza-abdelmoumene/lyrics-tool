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

It is also event-driven rather than a busy poll. Spawning ``playerctl`` ~8×/s
just to notice a pause or a seek cost ~10% of a core even with the music
paused. Instead one long-lived ``playerctl --follow`` process per followed
player reports track changes, play/pause and seeks the instant they happen;
real position reads run only in a short burst after each such event, which is
all the playback clock needs to lock on. Between events nothing is spawned.
"""
from __future__ import annotations

import atexit
import shutil
import subprocess
import sys
import threading
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
# the resolved choice (including "nothing to follow") for this long so we don't
# spawn a burst of playerctl processes on every poll; another player starting
# up is still picked up within a few seconds. While the followed player is
# actually playing, a switch is far less likely (and less urgent), so recheck
# less often.
_RESOLVE_TTL = 4.0
_RESOLVE_TTL_PLAYING = 10.0

# Follow the player with a persistent ``playerctl --follow`` instead of polling.
# Tests switch this off (or swap ``_Follower``) to stay hermetic.
FOLLOW_EVENTS = True

# After every player event (track change, play/pause, seek, follower start) the
# backend takes real position reads for this long. That's enough for the clock
# to lock on — through two second-ticks even for a whole-second player like
# cmus — after which the reads stop until the next event.
_BURST = 3.0

# A follow line whose position is off from the previous line's by more than
# this (after allowing for elapsed time) is a seek.
_SEEK_JUMP = 0.3

# Don't respawn a follower that keeps dying more often than this.
_FOLLOW_RETRY = 2.0

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


def _parse_state(text: str, sampled_at: float) -> Optional[NowPlaying]:
    """Parse one :data:`_STATE_FORMAT` line into a snapshot (``None`` if unusable)."""
    parts = text.strip().split("|||")
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
        sampled_at=sampled_at,
    )


def _is_event(prev: Optional[NowPlaying], cur: Optional[NowPlaying]) -> bool:
    """Whether ``cur`` is a real change from ``prev`` rather than a routine tick.

    ``playerctl --follow`` prints once a second while playing with a position it
    extrapolates itself; those ticks are not events. A new track, a status flip
    or a position that jumps off the extrapolated line (a seek) is.
    """
    if prev is None or cur is None:
        return True
    if (cur.status, cur.title, cur.artist, cur.trackid) != \
            (prev.status, prev.title, prev.artist, prev.trackid):
        return True
    expected = prev.position or 0.0
    if cur.status == "Playing":
        expected += cur.sampled_at - prev.sampled_at
    return abs((cur.position or 0.0) - expected) > _SEEK_JUMP


def _parent_death_signal():
    """``preexec_fn`` that makes the follower die with us (Linux ``prctl``).

    Resolved in the parent so the forked child only makes one C call — no
    imports or locks after fork. ``None`` where unavailable (BSD, no libc).
    """
    if not sys.platform.startswith("linux"):
        return None
    try:
        import ctypes
        import signal
        prctl = ctypes.CDLL(None, use_errno=True).prctl
        return lambda: prctl(1, int(signal.SIGTERM))  # 1 = PR_SET_PDEATHSIG
    except Exception:
        return None


class _Follower:
    """One ``playerctl --player P metadata --follow`` process and its reader.

    ``state`` is the latest parsed line; ``on_event`` fires (on the reader
    thread) whenever a line is a real change, and once more when the process
    ends — the player quit, or playerctl died.
    """

    def __init__(self, player: str, on_event) -> None:
        self.player = player
        self.state: Optional[NowPlaying] = None
        self.alive = True
        self._on_event = on_event
        self._proc = subprocess.Popen(
            ["playerctl", "--player", player, "metadata",
             "--format", _STATE_FORMAT, "--follow"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            text=True, bufsize=1, preexec_fn=_parent_death_signal(),
        )
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        try:
            for line in self._proc.stdout or ():
                cur = _parse_state(line, time.monotonic())
                event = _is_event(self.state, cur)
                self.state = cur
                if event:
                    self._on_event()
        except Exception:
            pass
        finally:
            self.alive = False
            self.state = None
            self._on_event()

    def close(self) -> None:
        self.alive = False
        try:
            self._proc.terminate()
            self._proc.wait(timeout=1)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass


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
        # Cached auto-detect result (instance name or None) + when it was taken
        # (0.0 = stale, re-resolve on the next call).
        self._resolved: Optional[str] = None
        self._resolved_at: float = 0.0
        # Event follower for the current player, and the real-read burst window.
        self._follow_enabled = FOLLOW_EVENTS
        self._follower: Optional[_Follower] = None
        self._follow_started = 0.0
        self._burst_until = 0.0
        self._last_read: Optional[NowPlaying] = None  # newest real position read
        atexit.register(self._stop_follower)

    @classmethod
    def available(cls) -> bool:
        return shutil.which("playerctl") is not None

    def set_player(self, name: Optional[str]) -> None:
        self._player = name or None
        self._resolved_at = 0.0  # drop any cached auto choice

    def set_ignored(self, names: Optional[str]) -> None:
        # ``None`` keeps the default block-list; '' disables ignoring entirely.
        self._ignored = DEFAULT_IGNORED_PLAYERS if names is None else names
        self._resolved_at = 0.0

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
        live = self._live_status()
        ttl = _RESOLVE_TTL_PLAYING if live.get(self._resolved) == "Playing" else _RESOLVE_TTL
        if self._resolved_at and (now - self._resolved_at) < ttl:
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
                status = live.get(player) or self._status_of(player)
                return (_STATUS_RANK.get(status, 2), music, idx)

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

    def _live_status(self) -> dict:
        """``{player: status}`` known for free from the follower (no spawn)."""
        f = self._follower
        if f is None or not f.alive or f.state is None:
            return {}
        return {f.player: f.state.status}

    # ── event following ──────────────────────────────────────────────────────
    def _on_event(self) -> None:
        self._burst_until = time.monotonic() + _BURST

    def _stop_follower(self) -> None:
        if self._follower is not None:
            self._follower.close()
            self._follower = None

    def _follow(self, player: str) -> Optional[_Follower]:
        """The live follower for ``player``, (re)starting it when needed."""
        f = self._follower
        if f is not None and f.player == player and f.alive:
            return f
        self._stop_follower()
        now = time.monotonic()
        if not self._follow_enabled or now - self._follow_started < _FOLLOW_RETRY:
            return None
        self._follow_started = now
        try:
            self._follower = _Follower(player, self._on_event)
        except Exception:
            self._follow_enabled = False  # can't follow → plain polling, as before
            return None
        self._on_event()
        return self._follower

    # ── snapshots ────────────────────────────────────────────────────────────
    def snapshot(self) -> Optional[NowPlaying]:
        """Current state; spawns a real read only around player events.

        Outside a burst, the follower's latest line supplies status and metadata
        and the position is the newest *real* read, unchanged — same
        ``sampled_at``, so the display loop sees no new sample and simply keeps
        free-running its clock. (The follower's own positions are playerctl's
        extrapolation, which for a whole-second player can sit up to a second
        off; they are only used to spot seeks.)
        """
        player = self._player or self._resolve_player()
        if player is None:
            self._stop_follower()
            return None
        follower = self._follow(player)
        live = follower.state if follower is not None and follower.alive else None
        last = self._last_read
        if (live is None or time.monotonic() < self._burst_until or last is None
                or (last.title, last.status) != (live.title, live.status)):
            snap = self._read_snapshot()
            if snap is not None:
                self._last_read = snap
            return snap
        return live._replace(position=last.position, sampled_at=last.sampled_at)

    def _read_snapshot(self) -> Optional[NowPlaying]:
        """One real ``playerctl metadata`` read of the followed player."""
        t0 = time.monotonic()
        result = self._run_playerctl(["metadata", "--format", _STATE_FORMAT])
        t1 = time.monotonic()

        if result is None or result.returncode != 0:
            # The followed player may have just vanished/stopped; re-resolve on
            # the next poll instead of clinging to a dead choice.
            self._resolved_at = 0.0
            return None

        return _parse_state(result.stdout, (t0 + t1) / 2)

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
