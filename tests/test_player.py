"""playerctl backend: auto-detect follows the playing music, never a browser
or a chat app's voice message."""
from lyrics_tool.players import playerctl
from lyrics_tool.players.playerctl import PlayerctlBackend


def _fake_world(monkeypatch, players):
    """Stand in for a live D-Bus: ``players`` maps instance name -> status.

    Patches the two enumeration probes so ``_resolve_player`` runs against a
    known set, and captures the command the *followed* player is queried with.
    """
    seen = {}

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(playerctl.subprocess, "run", fake_run)
    b = PlayerctlBackend()
    monkeypatch.setattr(b, "_list_players", lambda: list(players))
    monkeypatch.setattr(b, "_status_of", lambda p: players[p])
    return b, seen


def _followed(seen):
    cmd = seen.get("cmd")
    if cmd is None or "--player" not in cmd:
        return None
    return cmd[cmd.index("--player") + 1]


def test_auto_detect_ignores_browsers_and_chat_apps(monkeypatch):
    # The exact scenario that broke: a stopped Telegram voice message and a
    # paused YouTube tab must not win over the Spotify track.
    b, seen = _fake_world(monkeypatch, {
        "TelegramDesktop": "Stopped",
        "firefox.instance_1_57": "Paused",
        "spotify": "Paused",
    })
    assert b._resolve_player() == "spotify"
    b._run_playerctl(["status"])
    assert _followed(seen) == "spotify"


def test_prefers_the_playing_player(monkeypatch):
    # A playing local player beats a paused Spotify — follow the music that's on.
    b, _ = _fake_world(monkeypatch, {"spotify": "Paused", "mpv": "Playing"})
    assert b._resolve_player() == "mpv"


def test_music_priority_breaks_ties(monkeypatch):
    # Two players in the same state: the known music app (spotify) wins over an
    # unknown MPRIS source.
    b, _ = _fake_world(monkeypatch, {"some-random-app": "Playing", "spotify": "Playing"})
    assert b._resolve_player() == "spotify"


def test_only_ignored_players_means_idle(monkeypatch):
    # A lone Telegram voice message → nothing to follow → idle, not fake lyrics.
    b, _ = _fake_world(monkeypatch, {"TelegramDesktop": "Playing"})
    assert b._resolve_player() is None
    assert b._run_playerctl(["status"]) is None


def test_explicit_player_pin_skips_resolution(monkeypatch):
    b, seen = _fake_world(monkeypatch, {"TelegramDesktop": "Playing"})
    b.set_player("spotify")  # pin wins even when nothing else is followable
    b._run_playerctl(["status"])
    cmd = seen["cmd"]
    assert "--player" in cmd and "spotify" in cmd


def test_empty_ignore_follows_anything(monkeypatch):
    # Opt back into following everything: a chat app is now fair game.
    b, _ = _fake_world(monkeypatch, {"TelegramDesktop": "Playing"})
    b.set_ignored("")
    assert b._resolve_player() == "TelegramDesktop"


def test_resolution_is_cached(monkeypatch):
    # The 0.12 s poll must not re-enumerate every tick.
    calls = {"n": 0}
    b, _ = _fake_world(monkeypatch, {"spotify": "Playing"})

    def counting_list():
        calls["n"] += 1
        return ["spotify"]

    monkeypatch.setattr(b, "_list_players", counting_list)
    b._resolve_player()
    b._resolve_player()
    assert calls["n"] == 1  # second call served from cache


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
