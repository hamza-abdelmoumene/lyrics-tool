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

Note = Tuple[int, int, str]  # (row, col, glyph)


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
        self._particles = [
            {
                'col': rng.random(),                    # fractional column 0..1
                'rise': rng.uniform(0.018, 0.06),       # screens per second
                'phase': rng.random(),                  # vertical start offset
                'glyph': rng.choice(NOTE_GLYPHS),
                'sway_amp': rng.uniform(0.0, 3.0),      # columns
                'sway_speed': rng.uniform(0.2, 0.8),
                'sway_phase': rng.uniform(0.0, math.tau),
            }
            for _ in range(count)
        ]

    def positions(self, cols: int, rows: int, t: float) -> List[Note]:
        """Return on-screen ``(row, col, glyph)`` notes at time ``t`` seconds."""
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
                out.append((row, col, p['glyph']))
        return out
