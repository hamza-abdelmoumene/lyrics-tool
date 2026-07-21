"""Windows SMTC backend logic, tested through fakes (no winsdk, any OS).

Exercises the real snapshot-assembly path — status mapping, wall-clock position
extrapolation, and duration/title/album handling — by feeding ``_build_snapshot``
plain objects shaped like the winsdk timeline/media-properties it normally reads.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from lyrics_tool.players.windows import _PAUSED, _PLAYING, _build_snapshot, _status_name


def _timeline(pos, dur, last=None):
    return SimpleNamespace(
        position=timedelta(seconds=pos),
        start_time=timedelta(0),
        end_time=timedelta(seconds=dur),
        last_updated_time=last,
    )


def _props(title, artist="", album=""):
    return SimpleNamespace(title=title, artist=artist, album_title=album)


def test_status_mapping():
    assert _status_name(_PLAYING) == "Playing"
    assert _status_name(_PAUSED) == "Paused"
    assert _status_name(3) == "Stopped"       # Stopped
    assert _status_name(0) == "Stopped"       # Closed / unknown


def test_build_basic_paused():
    snap = _build_snapshot(_PAUSED, _timeline(30, 200), _props("T", "A", "Al"), 5.0)
    assert (snap.title, snap.artist, snap.album) == ("T", "A", "Al")
    assert snap.status == "Paused"
    assert snap.position == 30.0
    assert snap.duration == 200.0
    assert snap.sampled_at == 5.0
    assert snap.trackid is None


def test_position_extrapolated_while_playing():
    now = datetime(2020, 1, 1, 0, 0, 10, tzinfo=timezone.utc)
    last = datetime(2020, 1, 1, 0, 0, 7, tzinfo=timezone.utc)   # 3s ago
    snap = _build_snapshot(_PLAYING, _timeline(30, 200, last), _props("T"), 1.0, now=now)
    assert abs(snap.position - 33.0) < 1e-6                     # 30 + 3s elapsed


def test_no_extrapolation_when_paused():
    now = datetime(2020, 1, 1, 0, 0, 10, tzinfo=timezone.utc)
    last = datetime(2020, 1, 1, 0, 0, 7, tzinfo=timezone.utc)
    snap = _build_snapshot(_PAUSED, _timeline(30, 200, last), _props("T"), 1.0, now=now)
    assert snap.position == 30.0


def test_stale_gap_is_ignored():
    now = datetime(2020, 1, 1, 0, 0, 30, tzinfo=timezone.utc)
    last = datetime(2020, 1, 1, 0, 0, 7, tzinfo=timezone.utc)   # 23s > 5s cutoff
    snap = _build_snapshot(_PLAYING, _timeline(30, 200, last), _props("T"), 1.0, now=now)
    assert snap.position == 30.0


def test_naive_last_updated_treated_as_utc():
    now = datetime(2020, 1, 1, 0, 0, 10, tzinfo=timezone.utc)
    last = datetime(2020, 1, 1, 0, 0, 8)                        # naive → assume UTC
    snap = _build_snapshot(_PLAYING, _timeline(30, 200, last), _props("T"), 1.0, now=now)
    assert abs(snap.position - 32.0) < 1e-6


def test_no_title_returns_none():
    assert _build_snapshot(_PLAYING, _timeline(1, 1), _props(""), 1.0) is None


def test_zero_duration_is_none():
    snap = _build_snapshot(_PLAYING, _timeline(5, 0), _props("T"), 1.0)
    assert snap.duration is None


def test_empty_album_is_none():
    snap = _build_snapshot(_PAUSED, _timeline(5, 100), _props("T", "A", ""), 1.0)
    assert snap.album is None
