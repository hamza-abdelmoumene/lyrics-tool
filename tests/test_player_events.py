"""Event-driven playerctl backend: a persistent ``--follow`` process reports
changes, and real position reads happen only in a short burst after each one —
so an idle or steadily playing visualizer spawns nothing."""
import time

import pytest

from lyrics_tool.players import playerctl
from lyrics_tool.players.base import NowPlaying
from lyrics_tool.players.playerctl import PlayerctlBackend, _is_event, _parse_state

LINE = "Playing|||12500000|||Artist|||Title|||Album|||200000000|||/t/1"


def _np(status="Playing", position=10.0, title="Title", at=100.0):
    return NowPlaying(status, position, "Artist", title, None, 200.0, "/t/1", at)


def test_parse_state_reads_a_follow_line():
    s = _parse_state(LINE + "\n", 5.0)
    assert (s.status, s.position, s.title, s.album, s.duration) == \
        ("Playing", 12.5, "Title", "Album", 200.0)
    assert s.sampled_at == 5.0


def test_parse_state_rejects_blank_and_garbage():
    assert _parse_state("", 0.0) is None          # follower prints '' when the player quits
    assert _parse_state("nope", 0.0) is None


def test_routine_tick_is_not_an_event():
    # playerctl's once-a-second tick while playing: position advanced by the
    # elapsed time exactly.
    assert not _is_event(_np(position=10.0, at=100.0), _np(position=11.0, at=101.0))


def test_paused_repeat_is_not_an_event():
    assert not _is_event(_np("Paused", 10.0, at=100.0), _np("Paused", 10.0, at=130.0))


@pytest.mark.parametrize("cur", [
    _np(position=40.0, at=101.0),              # seek forward
    _np(position=3.0, at=101.0),               # seek back
    _np("Paused", 11.0, at=101.0),             # pause
    _np(title="Next", position=0.2, at=101.0),  # track change
    None,                                      # player went away
])
def test_changes_are_events(cur):
    assert _is_event(_np(position=10.0, at=100.0), cur)


class FakeFollower:
    """Stands in for ``_Follower``: no process, state set by the test."""
    instances = []

    def __init__(self, player, on_event):
        self.player, self.on_event = player, on_event
        self.state, self.alive = None, True
        FakeFollower.instances.append(self)

    def close(self):
        self.alive = False


@pytest.fixture
def backend(monkeypatch):
    FakeFollower.instances = []
    monkeypatch.setattr(playerctl, "_Follower", FakeFollower)
    reads = []

    class _Result:
        returncode = 0
        stdout = LINE

    def fake_run(cmd, **kw):
        reads.append(cmd)
        return _Result()

    monkeypatch.setattr(playerctl.subprocess, "run", fake_run)
    b = PlayerctlBackend()
    b._follow_enabled = True
    b.set_player("spotify")
    return b, reads


def test_reads_during_the_burst_then_goes_quiet(backend):
    b, reads = backend
    b.snapshot()                                  # starts the follower + a burst
    f = FakeFollower.instances[-1]
    f.state = _parse_state(LINE, time.monotonic())
    assert len(reads) == 1

    b.snapshot()                                  # still inside the burst → real read
    assert len(reads) == 2

    b._burst_until = 0.0                          # burst over
    before = len(reads)
    for _ in range(50):
        snap = b.snapshot()
    assert len(reads) == before                   # nothing spawned between events
    # Status/metadata come from the follower; the position is the last *real*
    # read, unchanged, so the clock sees no new sample and free-runs.
    assert snap.title == "Title" and snap.position == 12.5
    assert snap.sampled_at == b._last_read.sampled_at


def test_an_event_reopens_the_burst(backend):
    b, reads = backend
    b.snapshot()
    f = FakeFollower.instances[-1]
    f.state = _parse_state(LINE, time.monotonic())
    b._burst_until = 0.0
    b.snapshot()
    before = len(reads)
    f.on_event()                                  # e.g. a seek arrived
    b.snapshot()
    assert len(reads) == before + 1


def test_status_mismatch_forces_a_real_read(backend):
    # The follower already says Paused but our last real read says Playing
    # (the event raced the burst window) → read rather than mix the two.
    b, reads = backend
    b.snapshot()
    f = FakeFollower.instances[-1]
    f.state = _parse_state(LINE.replace("Playing", "Paused", 1), time.monotonic())
    b._burst_until = 0.0
    before = len(reads)
    b.snapshot()
    assert len(reads) == before + 1


def test_falls_back_to_polling_when_follow_cannot_start(monkeypatch):
    def boom(*a, **k):
        raise OSError("no playerctl")
    monkeypatch.setattr(playerctl, "_Follower", boom)

    class _Result:
        returncode = 0
        stdout = LINE
    calls = []
    monkeypatch.setattr(playerctl.subprocess, "run", lambda *a, **k: calls.append(a) or _Result())
    b = PlayerctlBackend()
    b._follow_enabled = True
    b.set_player("spotify")
    for _ in range(3):
        assert b.snapshot().title == "Title"
    assert len(calls) == 3 and b._follow_enabled is False


def test_switching_player_replaces_the_follower(backend):
    b, _ = backend
    b.snapshot()
    first = FakeFollower.instances[-1]
    b.set_player("cmus")
    b._follow_started = 0.0
    b.snapshot()
    assert not first.alive and FakeFollower.instances[-1].player == "cmus"
