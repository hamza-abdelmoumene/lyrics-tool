"""Player auto-detect must never follow a browser unless told to."""
import lyrics_tool.visualizer_player as P


def _capture(monkeypatch):
    seen = {}

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(P.subprocess, "run", fake_run)
    return seen


def test_auto_detect_ignores_browsers(monkeypatch):
    seen = _capture(monkeypatch)
    P.set_player(None)
    P.set_ignored(None)  # default browser list
    P._run_playerctl(["status"])
    cmd = seen["cmd"]
    assert "--ignore-player" in cmd
    ignored = cmd[cmd.index("--ignore-player") + 1]
    assert "firefox" in ignored and "chromium" in ignored
    assert "--player" not in cmd  # not pinned


def test_explicit_player_pin_skips_ignore(monkeypatch):
    seen = _capture(monkeypatch)
    P.set_player("spotify")
    P.set_ignored(None)
    P._run_playerctl(["status"])
    cmd = seen["cmd"]
    assert "--player" in cmd and "spotify" in cmd
    assert "--ignore-player" not in cmd  # an explicit pin wins
    P.set_player(None)  # reset global for other tests


def test_empty_ignore_follows_anything(monkeypatch):
    seen = _capture(monkeypatch)
    P.set_player(None)
    P.set_ignored("")  # opt back into following browsers
    P._run_playerctl(["status"])
    assert "--ignore-player" not in seen["cmd"]
    P.set_ignored(None)  # restore default for other tests
