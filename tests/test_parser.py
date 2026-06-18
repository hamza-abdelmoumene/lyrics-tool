import tempfile
import unittest
from pathlib import Path

from lrc_tools.parser import (
    parse_lrc,
    parse_lrc_simple,
    write_lrc,
    format_timestamp,
)


def _tmp(text: str) -> Path:
    p = Path(tempfile.mkstemp(suffix=".lrc")[1])
    p.write_text(text, encoding="utf-8")
    return p


class TestParser(unittest.TestCase):
    def test_parse_basic(self):
        lines = parse_lrc(_tmp("[00:12.34]hello\n[01:00.00]world\n# c\n\n"))
        self.assertEqual(len(lines), 2)
        self.assertAlmostEqual(lines[0]["timestamp"], 12.34, places=2)
        self.assertEqual(lines[0]["text"], "hello")
        self.assertAlmostEqual(lines[1]["timestamp"], 60.0, places=2)

    def test_sorted_by_time(self):
        lines = parse_lrc(_tmp("[01:00.00]b\n[00:10.00]a\n"))
        self.assertEqual([l["text"] for l in lines], ["a", "b"])

    def test_format_timestamp(self):
        self.assertEqual(format_timestamp(72.5), "[01:12.50]")

    def test_write_then_parse_roundtrip(self):
        src = parse_lrc(_tmp("[00:05.00]one two\n[00:09.00]three\n"))
        out = Path(tempfile.mkstemp(suffix=".lrc")[1])
        write_lrc(out, src)
        back = parse_lrc_simple(out)
        self.assertEqual(len(back), 2)
        self.assertEqual(back[0][1], "one two")
        self.assertAlmostEqual(back[0][0], 5.0, places=2)


if __name__ == "__main__":
    unittest.main()
