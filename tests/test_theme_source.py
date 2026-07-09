import json
import os
import tempfile
import unittest

from lyrics_tool.theme_source import (
    ArtColorProvider,
    Colors,
    FixedColorProvider,
    NullColorProvider,
    ThemeFileColorProvider,
    _dig,
    _hex_to_rgb,
    make_color_provider,
)


class TestHexParsing(unittest.TestCase):
    def test_full_and_short_and_bare(self):
        self.assertEqual(_hex_to_rgb("#00aaff"), (0, 170, 255))
        self.assertEqual(_hex_to_rgb("00aaff"), (0, 170, 255))
        self.assertEqual(_hex_to_rgb("#0af"), (0, 170, 255))  # short form expands

    def test_garbage_returns_none(self):
        self.assertIsNone(_hex_to_rgb("nope"))
        self.assertIsNone(_hex_to_rgb(""))
        self.assertIsNone(_hex_to_rgb(None))


class TestDig(unittest.TestCase):
    def test_nested_and_missing(self):
        data = {"colours": {"primary": "#112233"}, "flat": "#445566"}
        self.assertEqual(_dig(data, "colours.primary"), "#112233")
        self.assertEqual(_dig(data, "flat"), "#445566")
        self.assertIsNone(_dig(data, "colours.missing"))
        self.assertIsNone(_dig(data, "nope.at.all"))
        self.assertIsNone(_dig(data, None))


class TestFactory(unittest.TestCase):
    def test_named_sources(self):
        self.assertIsInstance(make_color_provider("art"), ArtColorProvider)
        self.assertIsInstance(make_color_provider("none"), NullColorProvider)
        self.assertIsInstance(make_color_provider("off"), NullColorProvider)
        self.assertIsInstance(make_color_provider("caelestia"), ThemeFileColorProvider)
        self.assertIsInstance(make_color_provider("pywal"), ThemeFileColorProvider)
        self.assertIsInstance(make_color_provider("wal"), ThemeFileColorProvider)  # alias

    def test_fixed_source(self):
        p = make_color_provider("fixed:#00aaff")
        self.assertIsInstance(p, FixedColorProvider)
        self.assertEqual(p.current(), Colors((0, 170, 255), None, None))

    def test_bad_fixed_falls_back_to_art(self):
        # A malformed fixed colour must never crash — degrade to portable default.
        self.assertIsInstance(make_color_provider("fixed:zzz"), ArtColorProvider)

    def test_unknown_source_falls_back_to_art(self):
        self.assertIsInstance(make_color_provider("nonsense"), ArtColorProvider)
        self.assertIsInstance(make_color_provider(None), ArtColorProvider)


class TestNullAndArtSafety(unittest.TestCase):
    def test_null_is_always_none(self):
        self.assertIsNone(NullColorProvider().current())

    def test_art_before_track_is_none(self):
        # No track announced yet → nothing resolved, must be None (not a crash).
        self.assertIsNone(ArtColorProvider().current())


class TestThemeFileProvider(unittest.TestCase):
    def _write(self, obj):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f)
        self.addCleanup(os.remove, path)
        return path

    def test_reads_material_you_style(self):
        path = self._write({
            "colours": {
                "primary": "#3355ff",
                "surfaceContainerHigh": "#111111",
                "onSurface": "#eeeeee",
            }
        })
        p = ThemeFileColorProvider(
            path, "colours.primary", "colours.surfaceContainerHigh", "colours.onSurface"
        )
        self.assertEqual(
            p.current(), Colors((51, 85, 255), (17, 17, 17), (238, 238, 238))
        )

    def test_reads_pywal_style_multiroot(self):
        path = self._write({
            "special": {"foreground": "#dddddd"},
            "colors": {"color0": "#000000", "color4": "#2288cc"},
        })
        p = ThemeFileColorProvider(path, "colors.color4", "colors.color0", "special.foreground")
        self.assertEqual(p.current(), Colors((34, 136, 204), (0, 0, 0), (221, 221, 221)))

    def test_missing_file_returns_none_not_crash(self):
        p = ThemeFileColorProvider("/no/such/theme.json", "colours.primary")
        self.assertIsNone(p.current())

    def test_continuous_flag(self):
        self.assertTrue(ThemeFileColorProvider("/x", "a").continuous)
        self.assertFalse(ArtColorProvider().continuous)


if __name__ == "__main__":
    unittest.main()
