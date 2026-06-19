import unittest
from io import BytesIO

from lrc_tools.render.cover import text_color, dominant_color, PIL_AVAILABLE
from lrc_tools.render import display as vd
from lrc_tools.render.fonts import get_font


def _png(rgb, size=(64, 64)) -> bytes:
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", size, rgb).save(buf, "PNG")
    return buf.getvalue()


class TestTextColor(unittest.TestCase):
    def test_dark_text_on_light_bg(self):
        self.assertEqual(text_color((255, 255, 255)), (18, 18, 18))
        self.assertEqual(text_color((240, 230, 120)), (18, 18, 18))

    def test_light_text_on_dark_bg(self):
        self.assertEqual(text_color((0, 0, 0)), (240, 240, 240))
        self.assertEqual(text_color((30, 20, 80)), (240, 240, 240))


@unittest.skipUnless(PIL_AVAILABLE, "Pillow not installed")
class TestDominantColor(unittest.TestCase):
    def test_solid_image_returns_that_colour(self):
        r, g, b = dominant_color(_png((200, 40, 40)))
        # Quantisation is near-exact for a flat image.
        self.assertTrue(abs(r - 200) < 20 and g < 60 and b < 60)

    def test_garbage_bytes_returns_none(self):
        self.assertIsNone(dominant_color(b"not an image"))


class TestTint(unittest.TestCase):
    def test_tint_wraps_every_row_with_bg(self):
        vd.get_terminal_size = lambda: (50, 14)
        vd._render_cache.clear()
        frame = vd.render_now_playing("Artist", "Song", get_font("block"))
        tinted = vd._tint_frame(frame, (200, 40, 40), (240, 240, 240))
        self.assertIn("48;2;200;40;40", tinted)
        self.assertIn("38;2;240;240;240", tinted)
        # Row count unchanged.
        self.assertEqual(frame.count("\n"), tinted.count("\n"))


if __name__ == "__main__":
    unittest.main()
