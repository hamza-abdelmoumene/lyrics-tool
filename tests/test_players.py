"""Backend selection, ad detection, and the macOS output parser.

All OS-independent: no playerctl, no winsdk, no nowplaying-cli required.
"""
import time

from lyrics_tool.players import (
    MacNowPlayingBackend,
    NullBackend,
    PlayerctlBackend,
    WindowsMediaBackend,
    backend_names,
    is_ad,
    select_backend,
)
from lyrics_tool.players.base import NowPlaying
from lyrics_tool.players.macos import _parse


def _np(**kw):
    base = dict(
        status="Playing", position=1.0, artist="A", title="T", album="Al",
        duration=100.0, trackid="t:1", sampled_at=time.monotonic(),
    )
    base.update(kw)
    return NowPlaying(**base)


# ── selection ────────────────────────────────────────────────────────────────

def test_prefer_by_alias_wins(monkeypatch):
    monkeypatch.delenv("LYRICSOOO_PLAYER_BACKEND", raising=False)
    assert isinstance(select_backend("windows"), WindowsMediaBackend)
    assert isinstance(select_backend("mac"), MacNowPlayingBackend)
    assert isinstance(select_backend("mpris"), PlayerctlBackend)
    assert isinstance(select_backend("none"), NullBackend)


def test_env_override(monkeypatch):
    monkeypatch.setenv("LYRICSOOO_PLAYER_BACKEND", "smtc")
    assert isinstance(select_backend(), WindowsMediaBackend)


def test_unknown_prefer_falls_through_to_auto(monkeypatch):
    monkeypatch.delenv("LYRICSOOO_PLAYER_BACKEND", raising=False)
    # None available -> NullBackend, never a crash.
    monkeypatch.setattr(PlayerctlBackend, "available", classmethod(lambda cls: False))
    monkeypatch.setattr(WindowsMediaBackend, "available", classmethod(lambda cls: False))
    monkeypatch.setattr(MacNowPlayingBackend, "available", classmethod(lambda cls: False))
    assert isinstance(select_backend("bogus-name"), NullBackend)


def test_auto_picks_first_available(monkeypatch):
    monkeypatch.delenv("LYRICSOOO_PLAYER_BACKEND", raising=False)
    monkeypatch.setattr(PlayerctlBackend, "available", classmethod(lambda cls: True))
    assert isinstance(select_backend(), PlayerctlBackend)


def test_backend_names():
    assert backend_names() == ["playerctl", "smtc", "nowplaying-cli"]


def test_null_backend_is_safe():
    b = NullBackend()
    assert b.snapshot() is None
    assert b.art_url() is None
    assert b.audio_file() is None
    assert b.track_full() is None
    b.set_player("x")   # no-ops, never raise
    b.set_ignored("y")


def test_track_full_derives_from_snapshot():
    b = NullBackend()
    b.snapshot = lambda: _np(artist="Queen", title="Bicycle", album="Jazz", duration=180.0)
    assert b.track_full() == ("Queen", "Bicycle", "Jazz", 180.0)


# ── ad detection ─────────────────────────────────────────────────────────────

def test_is_ad_by_trackid():
    assert is_ad(_np(trackid="spotify:ad:1234"))
    assert is_ad(_np(trackid="/com/spotify/ad/x"))


def test_is_ad_title_backup():
    assert is_ad(_np(artist="", title="Advertisement", trackid=None))
    assert not is_ad(_np(artist="Queen", title="Advertisement"))  # real artist -> track
    assert not is_ad(None)


# ── macOS parser ─────────────────────────────────────────────────────────────

def test_macos_parse_playing():
    lines = ["Bohemian Rhapsody", "Queen", "A Night at the Opera",
             "354.0", "42.13", "1.000000"]
    snap = _parse(lines, sampled_at=5.0)
    assert snap is not None
    assert snap.title == "Bohemian Rhapsody"
    assert snap.artist == "Queen"
    assert snap.status == "Playing"
    assert snap.position == 42.13
    assert snap.duration == 354.0


def test_macos_parse_paused_and_nulls():
    lines = ["Song", "Artist", "null", "null", "0", "0.0"]
    snap = _parse(lines, sampled_at=1.0)
    assert snap.status == "Paused"
    assert snap.album is None
    assert snap.duration is None
    assert snap.position == 0.0


def test_macos_parse_rejects_untitled():
    assert _parse(["", "Artist", "Al", "1", "1", "1"], 1.0) is None
    assert _parse(["only-two", "lines"], 1.0) is None


def test_macos_snapshot_via_subprocess(monkeypatch):
    from lyrics_tool.players import macos

    class _R:
        returncode = 0
        stdout = "Song\nArtist\nAlbum\n180.0\n12.0\n1.000000\n"
        stderr = ""

    monkeypatch.setattr(macos.subprocess, "run", lambda *a, **k: _R())
    snap = macos.MacNowPlayingBackend().snapshot()
    assert snap is not None
    assert snap.title == "Song" and snap.artist == "Artist"
    assert snap.status == "Playing" and snap.duration == 180.0


def test_macos_snapshot_none_on_error(monkeypatch):
    from lyrics_tool.players import macos

    class _R:
        returncode = 1
        stdout = ""
        stderr = "no session"

    monkeypatch.setattr(macos.subprocess, "run", lambda *a, **k: _R())
    assert macos.MacNowPlayingBackend().snapshot() is None
