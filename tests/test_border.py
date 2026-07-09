"""The spectrum border must keep the frame geometrically exact."""
import re

from lyrics_tool import visualizer_display as vd


def _vis(s: str) -> int:
    return len(re.sub(r"\x1b\[[0-9;]*m", "", s))


class _FakeSpec:
    def bars(self, n):
        return [0.5] * n


def test_get_terminal_size_insets_when_border_active(monkeypatch):
    monkeypatch.setattr(vd, "_real_size", lambda: (100, 30))
    vd.enable_border(_FakeSpec(), (200, 180, 100))
    try:
        assert vd.get_terminal_size() == (100 - 2 * vd._MX, 30 - 2 * vd._MY)
    finally:
        vd.disable_border()
    # back to real once disabled
    assert vd.get_terminal_size() == (100, 30)


def test_border_off_by_default(monkeypatch):
    monkeypatch.setattr(vd, "_real_size", lambda: (90, 24))
    vd.disable_border()
    assert vd.get_terminal_size() == (90, 24)
    assert vd.border_enabled() is False


def test_framed_output_is_exact_size(monkeypatch):
    monkeypatch.setattr(vd, "_real_size", lambda: (100, 30))
    vd.enable_border(_FakeSpec(), (200, 180, 100))
    try:
        iw, ih = 100 - 2 * vd._MX, 30 - 2 * vd._MY
        inner = "\n".join(" " * iw for _ in range(ih))
        framed = vd._frame_with_border(inner, 100, 30)
        rows = framed.split("\n")
        assert len(rows) == 30                       # exact height
        assert all(_vis(r) == 100 for r in rows)     # every row exact width
    finally:
        vd.disable_border()


def test_border_ignores_tiny_terminals(monkeypatch):
    # Too small to hold the frame → behave as if no border (no inset, no crash).
    monkeypatch.setattr(vd, "_real_size", lambda: (12, 5))
    vd.enable_border(_FakeSpec(), (200, 180, 100))
    try:
        assert vd._border_active() is False
        assert vd.get_terminal_size() == (12, 5)
    finally:
        vd.disable_border()


def test_resample():
    assert vd._resample([0.0, 1.0], 3) == [0.0, 0.5, 1.0]
    assert vd._resample([0.5, 0.5, 0.5, 0.5], 2) == [0.5, 0.5]
    assert vd._resample([], 3) == [0.0, 0.0, 0.0]
    assert vd._resample([0.2, 0.8], 2) == [0.2, 0.8]
