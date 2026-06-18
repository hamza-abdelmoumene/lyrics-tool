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


if __name__ == "__main__":
    unittest.main()
