"""Phase-locked playback clock for lyric sync.

The player publishes its position over MPRIS, but that number is noisy: every
``playerctl`` read carries subprocess + D-Bus latency, and players such as
Spotify quantise the value in coarse steps. The old visualizer took *one* such
sample at the start of each song and then free-ran on the monotonic clock,
re-anchoring only on a big (>0.5s) jump — so whatever jitter that single sample
happened to carry became a fixed offset for the whole track. Different songs got
different random offsets, which is exactly why the lyrics felt "always a little
early or a little late, differently every time".

``PlaybackClock`` fixes that. It keeps a smooth internal estimate of where
playback is *right now* and, on every fresh sample the monitor feeds it, eases
that estimate toward the player's timeline (a first-order phase-locked loop). A
bad initial anchor is quietly corrected within a second or two; a real seek or
track jump snaps immediately. Between samples it advances on the monotonic clock
so line changes stay frame-accurate without polling the player every frame.

The class is pure and deterministic — inject a fake ``monotonic`` to unit-test
convergence — and holds no I/O, so it stays trivially testable.
"""
import time

# Instantaneous error (seconds) above which we treat the sample as a genuine
# seek / track jump and snap the estimate straight onto it, rather than easing
# toward it. Small enough to catch a scrub, large enough that ordinary sampling
# jitter (tens of ms) never trips it.
HARD_SNAP = 0.5

# Fraction of the residual error folded in on each fresh sample. With the
# monitor sampling ~8x/second this eases onto the player's clock with a time
# constant of roughly a second — fast enough to erase a bad initial anchor,
# gentle enough that no correction is ever visible as a line jump under smooth
# playback.
SLEW_GAIN = 0.14

# Consecutive whole-second samples after which a player is treated as reporting
# a coarse, truncated position (cmus publishes whole seconds over MPRIS). Any
# fractional sample drops it straight back to precise.
COARSE_AFTER = 4

# How far past a whole second a sample may sit and still count as "whole".
# playerctl adds the few microseconds since it read the property (cmus's 6 s
# arrives as 6.000027), so exact equality never matches. One-sided and tight:
# a precise player lands here 4 samples running with odds of ~1e-8.
WHOLE_SLACK = 0.01


class QuantumDetector:
    """Learns whether a player's position is truncated to whole seconds.

    A coarse player's ``position=12`` really means "somewhere in [12, 13)".
    Treating it as exact makes the clock (and the seek detector) jump back by up
    to a second every second, which re-shows the previous lyric line. Feed every
    sample to :meth:`update`; :attr:`quantum` is 1.0 for a coarse player and 0.0
    for a precise one.
    """

    def __init__(self):
        self._whole_run = 0
        self.quantum = 0.0

    def update(self, position) -> float:
        if position > 0 and position - int(position) < WHOLE_SLACK:
            self._whole_run += 1
            if self._whole_run >= COARSE_AFTER:
                self.quantum = 1.0
        elif position > 0:
            self._whole_run = 0
            self.quantum = 0.0
        return self.quantum


class PlaybackClock:
    """A smooth, self-correcting estimate of raw playback position (seconds).

    "Raw" means the player's own timeline — no lyric lead / user offset baked
    in; the visualizer adds those when it selects a line, so the clock stays a
    faithful mirror of what the media widget shows.
    """

    def __init__(self, monotonic=time.monotonic):
        self._mono = monotonic
        self._anchor_pos = 0.0   # playback position at the anchor instant
        self._anchor_at = None   # monotonic instant of the anchor; None = frozen
        self._paused = False
        self._set = False        # False until the first reset/pause

    @property
    def paused(self) -> bool:
        return self._paused

    def reset(self, position, sampled_at=None, playing=True, quantum=0.0):
        """Hard-set the clock to a fresh sample.

        Used on the events where easing would be wrong: the first line of a
        track, a resume, or a detected seek — anywhere the estimate should jump
        straight to the truth. ``sampled_at`` (the monotonic instant the sample
        was taken) lets us compensate for the read latency so the anchor lands
        at *now*, not a few milliseconds ago. A coarse sample (``quantum`` > 0)
        only bounds the truth to ``[position, position + quantum)``; see
        :meth:`_settle` for where in that window we land.
        """
        if not playing:
            self.pause(position, quantum)
            return
        now = self._mono()
        latency = (now - sampled_at) if sampled_at is not None else 0.0
        self._anchor_pos = self._settle(position + latency, quantum)
        self._anchor_at = now
        self._paused = False
        self._set = True

    def pause(self, position, quantum=0.0):
        """Freeze the estimate at ``position`` (playback is paused)."""
        self._anchor_pos = self._settle(position, quantum)
        self._anchor_at = None
        self._paused = True
        self._set = True

    def _settle(self, lo, quantum):
        """Where to land for a sample that bounds the truth to ``[lo, lo+quantum]``.

        A precise sample is the answer. For a coarse one, keep our own running
        estimate when it already fits the window — it is sharper than the
        window, and snapping to the middle would jump up to half a second, e.g.
        back across a line on every pause/resume — otherwise take the middle.
        """
        if quantum and self._set and lo <= self.position() <= lo + quantum:
            return self.position()
        return lo + quantum / 2

    def position(self) -> float:
        """Best current estimate of raw playback position, in seconds."""
        if self._anchor_at is None:
            return self._anchor_pos
        return self._anchor_pos + (self._mono() - self._anchor_at)

    def correct(self, sample_pos, sampled_at, quantum=0.0) -> bool:
        """Fold a fresh player sample into the running estimate.

        Returns ``True`` when the error was large enough to snap (a seek/jump,
        so the caller should re-pick the current line immediately) and ``False``
        on an ordinary gentle slew. A no-op while paused.

        With ``quantum`` > 0 the sample is a window ``[pos, pos + quantum)``
        rather than a point: an estimate inside it is left alone and one outside
        is moved onto the nearest edge. The window is a hard bound — the truth is
        certainly inside it, give or take a few ms of read jitter — so the move
        is made in full rather than eased. Its edges move exactly when the
        player's reported second ticks over, so a sample either side of each
        tick pins the estimate to within one poll interval of the truth.
        """
        if self._anchor_at is None:
            return False
        now = self._mono()
        lo = sample_pos + (now - sampled_at)
        hi = lo + quantum
        our_now = self._anchor_pos + (now - self._anchor_at)
        if our_now < lo:
            err = lo - our_now
        elif our_now > hi:
            err = hi - our_now
        else:
            return False
        if abs(err) > HARD_SNAP:
            self._anchor_pos = (lo + hi) / 2
            self._anchor_at = now
            return True
        # Ease a fraction of the error into the anchor; the estimate keeps
        # free-running from the (nudged) anchor, so playback never stalls or
        # jerks — it just converges on the player's clock. A coarse window's
        # edge is exact, so it is taken whole.
        self._anchor_pos += err if quantum else err * SLEW_GAIN
        return False
