"""The selector must never block without a TTY, and must render its options."""
import re

from lyrics_tool import selector as S


def test_choose_returns_defaults_without_tty():
    # Under pytest stdin isn't a real TTY, so choose() short-circuits to defaults.
    assert S.choose(reveal="typewriter", wlrc=False) == {"reveal": "typewriter", "wlrc": False}
    assert S.choose(reveal="fade", wlrc=True) == {"reveal": "fade", "wlrc": True}


def test_render_contains_all_options():
    frame = S._render(S._FIELDS, sel=[0, 0], cursor=0,
                      accent=S._accent((219, 199, 102)), cols=64, rows=18)
    plain = re.sub(r"\x1b\[[0-9;]*m", "", frame)
    for word in ("Standard", "Typewriter", "Fade", "Glow", "Phrase", "Word",
                 "effect", "style"):
        assert word in plain


def test_decode_key_handles_arrows_and_letters():
    d = S._decode_key
    # arrow escape sequences (both normal and application-cursor variants)
    assert d(b"\x1b[A") == "up"
    assert d(b"\x1b[B") == "down"
    assert d(b"\x1b[C") == "right"
    assert d(b"\x1b[D") == "left"
    assert d(b"\x1bOA") == "up"
    # a lone escape cancels; an unknown sequence is treated as cancel
    assert d(b"\x1b") == "esc"
    assert d(b"\x1b[Z") == "esc"
    # confirm / vim keys / quit
    assert d(b"\r") == "enter"
    assert d(b"\n") == "enter"
    assert d(b" ") == "right"
    assert d(b"\t") == "down"
    assert d(b"j") == "down"
    assert d(b"k") == "up"
    assert d(b"h") == "left"
    assert d(b"l") == "right"
    assert d(b"q") == "esc"
    assert d(b"") == ""


def test_render_marks_active_row():
    frame = S._render(S._FIELDS, sel=[1, 0], cursor=1,
                      accent=S._accent((219, 199, 102)), cols=64, rows=18)
    plain = re.sub(r"\x1b\[[0-9;]*m", "", frame)
    # cursor on the 'style' row → its chosen chip is bracketed
    assert "[ Phrase ]" in plain
    assert "[ Typewriter ]" in plain  # effect row's selection index 1
