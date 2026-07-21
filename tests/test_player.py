"""playerctl backend: auto-detect must never follow a browser unless told to."""
from lyrics_tool.players import playerctl
from lyrics_tool.players.playerctl import PlayerctlBackend


def _capture(monkeypatch):
    seen = {}

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(playerctl.subprocess, "run", fake_run)
    return seen


def test_auto_detect_ignores_browsers(monkeypatch):
    seen = _capture(monkeypatch)
    b = PlayerctlBackend()  # default: auto-detect, browser list active
    b._run_playerctl(["status"])
    cmd = seen["cmd"]
    assert "--ignore-player" in cmd
    ignored = cmd[cmd.index("--ignore-player") + 1]
    assert "firefox" in ignored and "chromium" in ignored
    assert "--player" not in cmd  # not pinned


def test_explicit_player_pin_skips_ignore(monkeypatch):
    seen = _capture(monkeypatch)
    b = PlayerctlBackend()
    b.set_player("spotify")
    b._run_playerctl(["status"])
    cmd = seen["cmd"]
    assert "--player" in cmd and "spotify" in cmd
    assert "--ignore-player" not in cmd  # an explicit pin wins


def test_empty_ignore_follows_anything(monkeypatch):
    seen = _capture(monkeypatch)
    b = PlayerctlBackend()
    b.set_ignored("")  # opt back into following browsers
    b._run_playerctl(["status"])
    assert "--ignore-player" not in seen["cmd"]


def test_snapshot_parses_microseconds(monkeypatch):
    class _Result:
        returncode = 0
        # status|pos_us|artist|title|album|length_us|trackid
        stdout = "Playing|||30000000|||Queen|||Bohemian Rhapsody|||A Night|||354000000|||t:1\n"
        stderr = ""

    monkeypatch.setattr(playerctl.subprocess, "run", lambda *a, **k: _Result())
    snap = PlayerctlBackend().snapshot()
    assert snap is not None
    assert snap.title == "Bohemian Rhapsody"
    assert snap.position == 30.0          # microseconds -> seconds
    assert snap.duration == 354.0
    assert snap.artist == "Queen"


def test_snapshot_none_when_no_title(monkeypatch):
    class _Result:
        returncode = 0
        stdout = "Playing|||1000000|||||||||||||\n"  # blank title, not an ad
        stderr = ""

    monkeypatch.setattr(playerctl.subprocess, "run", lambda *a, **k: _Result())
    assert PlayerctlBackend().snapshot() is None
