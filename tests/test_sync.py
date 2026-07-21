"""Tests for the phase-locked playback clock.

Uses a fake monotonic clock so convergence is deterministic — no sleeps, no
player. These pin the behaviour that fixes the "always a little early/late"
drift: a bad initial anchor must be eased away, a real seek must snap, and a
pause must freeze the estimate.
"""
import unittest

from lyrics_tool.sync import PlaybackClock, HARD_SNAP, SLEW_GAIN


class FakeClock:
    """Manually-advanced monotonic source."""

    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def tick(self, dt):
        self.t += dt
        return self.t


class PlaybackClockTest(unittest.TestCase):
    def test_reset_compensates_read_latency(self):
        mono = FakeClock()
        clk = PlaybackClock(monotonic=mono)
        # Sample says pos=10.0, taken 0.2s ago → estimate should read ~10.2 now.
        clk.reset(10.0, sampled_at=mono.t - 0.2)
        self.assertAlmostEqual(clk.position(), 10.2, places=6)

    def test_position_advances_with_the_clock(self):
        mono = FakeClock()
        clk = PlaybackClock(monotonic=mono)
        clk.reset(5.0, sampled_at=mono.t)
        mono.tick(2.0)
        self.assertAlmostEqual(clk.position(), 7.0, places=6)

    def test_pause_freezes_the_estimate(self):
        mono = FakeClock()
        clk = PlaybackClock(monotonic=mono)
        clk.pause(42.0)
        self.assertTrue(clk.paused)
        mono.tick(10.0)
        self.assertEqual(clk.position(), 42.0)
        # A correction while paused is a no-op.
        self.assertFalse(clk.correct(99.0, mono.t))
        self.assertEqual(clk.position(), 42.0)

    def test_gentle_slew_does_not_snap(self):
        mono = FakeClock()
        clk = PlaybackClock(monotonic=mono)
        clk.reset(0.0, sampled_at=mono.t)
        # Player is 0.2s ahead of us — a small error, so it must slew, not snap.
        snapped = clk.correct(0.2, mono.t)
        self.assertFalse(snapped)
        # Only a fraction of the error is folded in on one sample.
        self.assertAlmostEqual(clk.position(), 0.2 * SLEW_GAIN, places=6)

    def test_slew_converges_over_repeated_samples(self):
        mono = FakeClock()
        clk = PlaybackClock(monotonic=mono)
        clk.reset(0.0, sampled_at=mono.t)
        # The player runs 0.3s ahead of our anchor the whole time. Feed samples
        # at 8 Hz; the estimate should close almost all of the gap within ~1.5s.
        for _ in range(12):
            mono.tick(0.125)
            player_pos = clk.position() + 0.3  # persistent 0.3s lead
            clk.correct(player_pos, mono.t)
        # Residual error is a small fraction of the original 0.3s gap.
        residual = 0.3 * (1 - SLEW_GAIN) ** 12
        self.assertLess(residual, 0.06)

    def test_large_jump_snaps_immediately(self):
        mono = FakeClock()
        clk = PlaybackClock(monotonic=mono)
        clk.reset(10.0, sampled_at=mono.t)
        # A scrub to 90s is well beyond HARD_SNAP → snap straight there.
        self.assertGreater(90.0 - 10.0, HARD_SNAP)
        snapped = clk.correct(90.0, mono.t)
        self.assertTrue(snapped)
        self.assertAlmostEqual(clk.position(), 90.0, places=6)

    def test_reset_playing_false_pauses(self):
        mono = FakeClock()
        clk = PlaybackClock(monotonic=mono)
        clk.reset(3.0, sampled_at=mono.t, playing=False)
        self.assertTrue(clk.paused)
        mono.tick(5.0)
        self.assertEqual(clk.position(), 3.0)


if __name__ == "__main__":
    unittest.main()
