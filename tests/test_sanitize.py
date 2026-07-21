"""Untrusted lyric/metadata text must not carry terminal escape sequences."""
from lyrics_tool import visualizer_display as vd
from lyrics_tool.fonts import get_font


def test_sanitize_strips_escape_and_controls():
    s = vd.sanitize_text
    assert s("\x1b[2J\x1b[31mHACK") == "[2J[31mHACK"   # ESC removed, letters survive
    assert s("clean lyric") == "clean lyric"
    assert s("bell\x07null\x00") == "bellnull"
    assert s("keep\ttab\nnewline") == "keep\ttab\nnewline"  # tab/newline preserved
    assert s("") == ""


def test_render_output_has_no_injected_escapes():
    # A crafted title that tries to clear the screen and move the cursor must
    # not reach the terminal as a live escape sequence.
    evil = "\x1b[2J\x1b[HGotcha"
    frame = vd.render_now_playing(evil, evil, get_font("block"))
    # The only ESC left in the frame is the renderer's own reset/colour codes —
    # never the payload. The literal "[2J" survives as harmless text at most.
    assert "\x1b[2J" not in frame
    assert "\x1b[H" not in frame


def test_simple_text_sanitized():
    frame = vd.render_simple_text("\x1b[5mblink", centered=False)
    assert "\x1b[5m" not in frame
