import unittest

from lrc_tools.parser.processor import (
    phrases_to_words,
    process_long_phrases,
    count_syllables,
)


class TestProcessor(unittest.TestCase):
    def test_phrases_to_words_order_and_timing(self):
        phrases = [
            {"timestamp": 10.0, "text": "alpha beta gamma"},
            {"timestamp": 13.0, "text": "delta"},
        ]
        words = phrases_to_words(phrases)
        self.assertEqual([w["text"] for w in words], ["alpha", "beta", "gamma", "delta"])
        ts = [w["timestamp"] for w in words]
        self.assertTrue(all(ts[i] <= ts[i + 1] for i in range(len(ts) - 1)))
        # words stay within their phrase window
        self.assertGreaterEqual(words[0]["timestamp"], 10.0)
        self.assertLess(words[1]["timestamp"], 13.0)

    def test_empty_phrase_does_not_crash(self):
        # whitespace-only phrase used to divide by zero (len(words)==0)
        phrases = [{"timestamp": 1.0, "text": "   "}, {"timestamp": 2.0, "text": "word"}]
        words = phrases_to_words(phrases)  # must not raise
        self.assertEqual([w["text"] for w in words], ["word"])

    def test_count_syllables_min_one(self):
        self.assertGreaterEqual(count_syllables("hello"), 1)
        self.assertEqual(count_syllables(""), 1)

    def test_process_long_phrases_preserves_words(self):
        lines = [
            {"timestamp": 0.0, "text": "one, two, three"},
            {"timestamp": 6.0, "text": "end"},
        ]
        out = process_long_phrases(lines, total_duration=10.0)
        self.assertGreaterEqual(len(out), 1)
        got = {w for ln in out for w in ln["text"].replace(",", " ").split()}
        self.assertTrue({"one", "two", "three", "end"} <= got)


if __name__ == "__main__":
    unittest.main()
