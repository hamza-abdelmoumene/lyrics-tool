"""Cross-platform key input: decoding and no-TTY safety."""
from lyrics_tool import keyinput as k


def test_decode_arrows_and_letters():
    assert k.decode_key(b"\x1b[A") == "up"
    assert k.decode_key(b"\x1b[B") == "down"
    assert k.decode_key(b"\x1bOC") == "right"  # application-cursor variant
    assert k.decode_key(b"\x1b") == "esc"
    assert k.decode_key(b"\x1b[Z") == "esc"    # unknown sequence -> cancel
    assert k.decode_key(b"j") == "down"
    assert k.decode_key(b"\r") == "enter"
    assert k.decode_key(b"") == ""


def test_windows_arrow_table_complete():
    # Every arrow the picker cares about has a Windows scan-code mapping.
    assert set(k._WIN_ARROWS.values()) == {"up", "down", "left", "right"}


def test_keyreader_is_noop_without_tty():
    # Under pytest stdin isn't interactive, so the reader stays inert and never
    # touches termios/msvcrt or blocks.
    with k.KeyReader() as r:
        assert r.get() is None
        assert r.get() is None


def test_enable_ansi_safe_everywhere():
    k.enable_ansi()  # must never raise, on any platform


def test_raw_mode_restores(monkeypatch):
    # Simulate Windows: raw_mode must be an inert context manager there.
    monkeypatch.setattr(k, "IS_WINDOWS", True)
    with k.raw_mode(0):
        pass  # no termios calls on the Windows path
