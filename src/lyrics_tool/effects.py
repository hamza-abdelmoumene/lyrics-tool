"""
Ambient background effects for the lyric view.

A lightweight particle field of music notes that drift up the screen behind
the lyrics. It is pure-math and stateless per frame (positions are a function
of wall-clock time), so it is cheap, deterministic, and trivially testable.
"""
import math
import random
from typing import List, Tuple

# Reliably narrow (width-1) music glyphs in modern terminals.
NOTE_GLYPHS = ['♪', '♫', '♩', '♬', '♭', '♮']

Note = Tuple[int, int, str, int]  # (row, col, glyph, grey-shade)

# 256-colour grey ramp the notes are painted in: GREY_MIN is barely-there (used
# at the top/bottom edges so notes twinkle in and out rather than popping), up to
# GREY_SOFT for the nearest notes — still dim enough to sit behind the lyric.
GREY_MIN = 234
GREY_SOFT = 249

# Fraction of a note's travel spent fading in (at the bottom) / out (at the top).
_EDGE = 0.16


class NoteField:
    """A drifting field of music notes sized to the terminal.

    Particles are seeded once (so the pattern is stable) and given fractional
    columns, so the field rescales cleanly when the terminal is resized. Each
    particle rises at its own pace, wraps around, and sways sideways.
    """

    def __init__(self, density: float = 1.0, seed: int = 1337):
        self._density = density
        self._rng = random.Random(seed)
        self._particles: List[dict] = []
        self._for_area = (-1, -1)

    def _ensure(self, cols: int, rows: int) -> None:
        """(Re)build the particle pool when the terminal area changes."""
        if (cols, rows) == self._for_area:
            return
        self._for_area = (cols, rows)
        count = max(4, int(cols * rows * 0.012 * self._density))
        rng = self._rng
        particles = []
        for _ in range(count):
            # Depth (0 = far, 1 = near) drives a gentle parallax: nearer notes
            # rise a touch faster, sway a touch wider, and glow a touch brighter.
            depth = rng.random()
            particles.append({
                'col': rng.random(),                        # fractional column 0..1
                'depth': depth,
                'rise': 0.02 + depth * 0.045,               # screens per second
                'phase': rng.random(),                      # vertical start offset
                'glyph': rng.choice(NOTE_GLYPHS),
                'sway_amp': rng.uniform(0.0, 2.0) + depth,  # columns
                'sway_speed': rng.uniform(0.2, 0.8),
                'sway_phase': rng.uniform(0.0, math.tau),
            })
        self._particles = particles

    def positions(self, cols: int, rows: int, t: float) -> List[Note]:
        """Return on-screen ``(row, col, glyph, shade)`` notes at time ``t``.

        ``shade`` is a 256-colour grey: brighter for nearer notes (depth), and
        faded toward :data:`GREY_MIN` over the first/last :data:`_EDGE` of each
        note's travel so notes twinkle in at the bottom and out at the top.
        """
        if cols <= 0 or rows <= 0:
            return []
        self._ensure(cols, rows)
        span = rows + 2  # rise off the top before wrapping back in at the bottom
        out: List[Note] = []
        for p in self._particles:
            frac = (t * p['rise'] + p['phase']) % 1.0
            row = int(round((1.0 - frac) * span)) - 1
            sway = p['sway_amp'] * math.sin(t * p['sway_speed'] + p['sway_phase'])
            col = int(round(p['col'] * (cols - 1) + sway))
            if 0 <= row < rows and 0 <= col < cols:
                # Edge twinkle: ramp brightness up just after entering (low frac)
                # and back down before exiting (high frac).
                if frac < _EDGE:
                    fade = frac / _EDGE
                elif frac > 1.0 - _EDGE:
                    fade = (1.0 - frac) / _EDGE
                else:
                    fade = 1.0
                bright = (0.4 + 0.6 * p['depth']) * fade
                shade = GREY_MIN + int(round(bright * (GREY_SOFT - GREY_MIN)))
                out.append((row, col, p['glyph'], shade))
        return out


# ── premium per-line reveal effects (opt-in, one selected at a time) ─────────
# Pure colour maths so they stay cheap and testable: given the lyric accent and
# how long the current line has been on screen, return the colour to paint it
# this frame. 'standard'/'typewriter' don't recolour (they return the base as-is
# — typewriter animates the *text*, handled in the loop). 'fade' eases a line in
# from dim → full when it appears; 'glow' gives the active line a soft, endless
# breathing pulse. Both look their best on a dark terminal.
FADE_IN = 0.40        # seconds a 'fade' line takes to reach full brightness
GLOW_HZ = 0.5         # 'glow' breathing rate (cycles per second)
_FALLBACK_ACCENT = (230, 230, 230)   # base used when no colour source is active

REVEALS = ("standard", "typewriter", "fade", "glow")


def _dim(color: Tuple[int, int, int], f: float) -> Tuple[int, int, int]:
    """Scale ``color`` toward black by factor ``f`` (0 → black, 1 → unchanged)."""
    f = max(0.0, min(1.0, f))
    return tuple(int(round(c * f)) for c in color)


def line_effect_color(base, mode: str, elapsed: float, paused: bool = False):
    """Colour for the current lyric line under reveal ``mode``.

    ``base`` is the accent RGB (or ``None`` = terminal default). ``elapsed`` is
    seconds since the line appeared. Returns an RGB tuple, or ``None`` to keep
    the terminal default (only for modes that don't recolour).
    """
    if mode not in ("fade", "glow"):
        return base
    b = base or _FALLBACK_ACCENT
    if mode == "fade":
        f = 0.15 + 0.85 * min(1.0, max(0.0, elapsed) / FADE_IN)   # dim → full
        return _dim(b, f)
    # glow: gentle continuous breathing, frozen while paused.
    phase = 0.0 if paused else max(0.0, elapsed)
    f = 0.78 + 0.22 * (0.5 + 0.5 * math.sin(phase * GLOW_HZ * math.tau))
    return _dim(b, f)


def effect_animating(mode: str, elapsed: float) -> bool:
    """Whether ``mode`` still needs per-frame repaints at ``elapsed`` seconds."""
    if mode == "fade":
        return elapsed < FADE_IN
    return mode == "glow"        # glow breathes forever
