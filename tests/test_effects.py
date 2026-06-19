import unittest

from lrc_tools.effects import NoteField, NOTE_GLYPHS
from lrc_tools import visualizer_display as vd
from lrc_tools.fonts import get_font


class TestNoteField(unittest.TestCase):
    def test_positions_stay_in_bounds(self):
        nf = NoteField()
        for cols, rows in [(80, 24), (40, 12), (120, 30)]:
            for t in (0.0, 0.7, 3.3, 9.1, 25.0):
                for r, c, g in nf.positions(cols, rows, t):
                    self.assertTrue(0 <= r < rows)
                    self.assertTrue(0 <= c < cols)
                    self.assertIn(g, NOTE_GLYPHS)

    def test_deterministic_for_same_seed(self):
        a = NoteField(seed=42).positions(80, 24, 4.0)
        b = NoteField(seed=42).positions(80, 24, 4.0)
        self.assertEqual(a, b)

    def test_notes_move_over_time(self):
        nf = NoteField()
        first = nf.positions(80, 24, 0.0)
        later = nf.positions(80, 24, 8.0)
        self.assertNotEqual(first, later)

    def test_zero_area_is_empty(self):
        self.assertEqual(NoteField().positions(0, 0, 1.0), [])


class TestOverlay(unittest.TestCase):
    def setUp(self):
        self.font = get_font("block")
        vd._render_cache.clear()
        vd.get_terminal_size = lambda: (60, 18)

    def test_overlay_preserves_grid_shape(self):
        base = vd.render_block_text("HELLO", self.font)
        notes = NoteField().positions(60, 18, 3.0)
        framed = vd._overlay_notes(base, notes)
        # Same number of rows, and visible width per row unchanged (ANSI is
        # zero-width, each glyph replaces exactly one space cell).
        base_rows = base.split("\n")
        out_rows = framed.split("\n")
        self.assertEqual(len(base_rows), len(out_rows))
        for b, o in zip(base_rows, out_rows):
            self.assertEqual(len(b), _visible_len(o))

    def test_notes_never_cover_letters(self):
        base = vd.render_block_text("X", self.font)
        # A note targeting a non-blank cell must be ignored.
        rows = base.split("\n")
        target = next((r, c) for r, line in enumerate(rows)
                      for c, ch in enumerate(line) if ch != " ")
        framed = vd._overlay_notes(base, [(target[0], target[1], "X")])
        self.assertEqual(framed, base)


def _visible_len(s: str) -> int:
    """Length of a string ignoring SGR escape sequences."""
    import re
    return len(re.sub(r"\033\[[0-9;]*m", "", s))


if __name__ == "__main__":
    unittest.main()
