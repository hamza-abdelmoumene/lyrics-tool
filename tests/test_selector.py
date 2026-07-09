"""The selector must never block without a TTY, and must render its options."""
import re

from lyrics_tool import selector as S


def test_choose_returns_defaults_without_tty():
    # Under pytest stdin isn't a real TTY, so choose() short-circuits to defaults.
    assert S.choose(typewriter=True, wlrc=False) == {"typewriter": True, "wlrc": False}
    assert S.choose(typewriter=False, wlrc=True) == {"typewriter": False, "wlrc": True}


def test_render_contains_all_options():
    frame = S._render(S._FIELDS, sel=[0, 0], cursor=0,
                      accent=S._accent((219, 199, 102)), cols=64, rows=18)
    plain = re.sub(r"\x1b\[[0-9;]*m", "", frame)
    for word in ("Typewriter", "Standard", "Phrase", "Word", "effect", "style"):
        assert word in plain


def test_render_marks_active_row():
    frame = S._render(S._FIELDS, sel=[1, 0], cursor=1,
                      accent=S._accent((219, 199, 102)), cols=64, rows=18)
    plain = re.sub(r"\x1b\[[0-9;]*m", "", frame)
    # cursor on the 'style' row → its chosen chip is bracketed
    assert "[ Phrase ]" in plain
    assert "[ Standard ]" in plain  # effect row's selection index 1
