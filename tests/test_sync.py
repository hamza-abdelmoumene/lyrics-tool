"""Tests for the phase-locked playback clock.

Uses a fake monotonic clock so convergence is deterministic — no sleeps, no
player. These pin the behaviour that fixes the "always a little early/late"
drift: a bad initial anchor must be eased away, a real seek must snap, and a
pause must freeze the estimate.
"""
import unittest

import math
import threading
import time
from types import SimpleNamespace

from lyrics_tool.sync import (
    COARSE_AFTER, HARD_SNAP, SLEW_GAIN, PlaybackClock, QuantumDetector,
)


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
        start = mono.t
        for _ in range(12):
            mono.tick(0.125)
            player_pos = 0.3 + (mono.t - start)  # player truly 0.3s ahead
            clk.correct(player_pos, mono.t)
        # Residual error is a small fraction of the original 0.3s gap.
        residual = (0.3 + (mono.t - start)) - clk.position()
        self.assertAlmostEqual(residual, 0.3 * (1 - SLEW_GAIN) ** 12, places=6)
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



class CoarsePositionTest(unittest.TestCase):
    """Players like cmus report whole seconds; truncation must not read as drift.

    Regression for issue #9: the previous line flashed back after each new one
    because every second tick of a truncated position looked like a seek.
    """

    def test_detector_flags_whole_second_players(self):
        det = QuantumDetector()
        for pos in range(1, COARSE_AFTER):
            self.assertEqual(det.update(float(pos)), 0.0)
        self.assertEqual(det.update(float(COARSE_AFTER)), 1.0)

    def test_detector_drops_back_on_a_fractional_sample(self):
        det = QuantumDetector()
        for pos in range(1, COARSE_AFTER + 1):
            det.update(float(pos))
        self.assertEqual(det.update(12.37), 0.0)

    def test_detector_ignores_zero(self):
        det = QuantumDetector()
        for _ in range(COARSE_AFTER * 2):
            det.update(0.0)  # stopped / track start — says nothing
        self.assertEqual(det.quantum, 0.0)

    def test_reset_lands_mid_window(self):
        mono = FakeClock()
        clk = PlaybackClock(monotonic=mono)
        clk.reset(12.0, sampled_at=mono.t, quantum=1.0)
        self.assertAlmostEqual(clk.position(), 12.5, places=6)

    def test_estimate_inside_window_is_left_alone(self):
        mono = FakeClock()
        clk = PlaybackClock(monotonic=mono)
        clk.reset(12.7, sampled_at=mono.t)
        # "12" from a coarse player means [12, 13) — 12.7 is consistent with it.
        self.assertFalse(clk.correct(12.0, mono.t, quantum=1.0))
        self.assertAlmostEqual(clk.position(), 12.7, places=6)

    def test_seek_snaps_to_window_middle(self):
        mono = FakeClock()
        clk = PlaybackClock(monotonic=mono)
        clk.reset(10.0, sampled_at=mono.t)
        self.assertTrue(clk.correct(90.0, mono.t, quantum=1.0))
        self.assertAlmostEqual(clk.position(), 90.5, places=6)

    def test_truncated_samples_never_drag_the_clock_back(self):
        mono = FakeClock()
        clk = PlaybackClock(monotonic=mono)
        true0 = 30.25
        start = mono.t
        clk.reset(math.floor(true0), sampled_at=mono.t, quantum=1.0)
        prev = clk.position()
        for _ in range(400):  # 50 s of 8 Hz samples
            mono.tick(0.125)
            true = true0 + (mono.t - start)
            clk.correct(float(math.floor(true)), mono.t, quantum=1.0)
            now = clk.position()
            self.assertGreaterEqual(now, prev)  # playback never runs backwards
            prev = now
        # And it has converged onto the true position, not a second behind it.
        self.assertLess(abs(clk.position() - true), 0.13)


class CoarseMonitorTest(unittest.TestCase):
    def test_monitor_does_not_mistake_truncation_for_seeks(self):
        from lyrics_tool.visualizer_main import SyncData, position_monitor

        t0 = time.monotonic() - 20.4

        def get_state():
            now = time.monotonic()
            return SimpleNamespace(title='song', status='Playing',
                                   position=float(math.floor(now - t0)),
                                   sampled_at=now)

        sd = SyncData()
        sd.current_title = 'song'
        thread = threading.Thread(target=position_monitor, args=(sd, get_state),
                                  daemon=True)
        thread.start()
        try:
            # Let the detector learn the player is coarse, then watch 2.5 s of
            # playback (two-plus second ticks) for spurious seeks.
            time.sleep(0.12 * (COARSE_AFTER + 1))
            sd.should_resync = False
            time.sleep(2.5)
            self.assertEqual(sd.quantum, 1.0)
            self.assertFalse(sd.should_resync)
        finally:
            sd.running = False
            thread.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
