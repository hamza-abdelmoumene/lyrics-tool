import unittest

from lrc_tools import visualizer_display as vd
from lrc_tools.fonts import get_font


class TestRender(unittest.TestCase):
    def setUp(self):
        self.font = get_font("block")
        vd._render_cache.clear()

    def _frame(self, text, cols, rows):
        vd.get_terminal_size = lambda: (cols, rows)
        return vd.render_block_text(text, self.font)

    def test_short_text_fits_every_size(self):
        for cols, rows in [(80, 24), (40, 24), (30, 20), (120, 30)]:
            lines = self._frame("LOVE", cols, rows).split("\n")
            self.assertLessEqual(len(lines), rows)
            self.assertTrue(all(len(l) <= cols for l in lines))

    def test_long_text_wraps_in_bounds(self):
        lines = self._frame("EVERYTHING I WANTED RIGHT NOW TONIGHT", 60, 24).split("\n")
        self.assertLessEqual(len(lines), 24)
        self.assertTrue(all(len(l) <= 60 for l in lines))

    def test_word_wider_than_terminal_falls_back_plain(self):
        lines = self._frame("SUPERCALIFRAGILISTIC", 10, 24).split("\n")
        self.assertTrue(all(len(l) <= 10 for l in lines))

    def test_render_cache_returns_same_object(self):
        vd.get_terminal_size = lambda: (80, 24)
        vd._render_cache.clear()
        a = vd.render_block_text("CACHE", self.font)
        b = vd.render_block_text("CACHE", self.font)
        self.assertIs(a, b)


def _visible_len(s: str) -> int:
    """Length of a string ignoring SGR escape sequences."""
    import re
    return len(re.sub(r"\033\[[0-9;]*m", "", s))


class TestIdleScreens(unittest.TestCase):
    """The waiting / searching / no-lyrics / ad screens that keep the view alive."""

    def setUp(self):
        self.font = get_font("block")
        vd._render_cache.clear()
        vd.get_terminal_size = lambda: (60, 18)

    def test_status_frame_is_rectangular(self):
        # Every idle screen is a cols x rows grid of full-width rows.
        frame = vd._render_status(["finding lyrics", "", "Some Song Title"])
        rows = frame.split("\n")
        self.assertEqual(len(rows), 18)
        self.assertTrue(all(len(r) == 60 for r in rows))

    def test_status_notes_keep_visible_width(self):
        from lrc_tools.effects import NoteField
        notes = NoteField().positions(60, 18, 3.0)
        frame = vd._render_status(["x"], notes=notes)
        for row in frame.split("\n"):
            self.assertEqual(_visible_len(row), 60)

    def test_ad_screen_animates_across_phases(self):
        # The bored face / snooze trail must actually change as phase advances.
        a = vd.render_ad_screen(self.font, phase=0)
        b = vd.render_ad_screen(self.font, phase=1)
        self.assertNotEqual(a, b)

    def _paint_silently(self, fn, *args, **kwargs):
        """Call a display_* helper, capturing its terminal writes."""
        import contextlib, io
        vd._last_frame = None
        with contextlib.redirect_stdout(io.StringIO()):
            fn(*args, **kwargs)
        return vd._last_frame

    def test_searching_paints_title(self):
        # display_searching should paint the song title into the frame it emits.
        frame = self._paint_silently(vd.display_searching, "Unique Title Here", phase=0)
        self.assertIn("Unique Title Here", frame)

    def test_no_lyrics_paints_title(self):
        frame = self._paint_silently(vd.display_no_lyrics, "Another Song")
        self.assertIn("Another Song", frame)


if __name__ == "__main__":
    unittest.main()
