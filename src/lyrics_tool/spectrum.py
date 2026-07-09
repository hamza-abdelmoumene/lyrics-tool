"""
Audio spectrum via ``cava`` — optional, for the reactive border frame.

Runs ``cava`` as a subprocess in raw-stdout mode and reads its bar values on a
daemon thread, so the visualiser can draw a live equaliser around the lyrics
without blocking. Everything degrades gracefully: if ``cava`` isn't installed
or won't start, :meth:`Spectrum.bars` returns ``None`` and the caller simply
skips the frame — no dependency, no crash.

``cava`` handles the audio capture itself (PipeWire / PulseAudio monitor), so
this needs no audio libraries. Values are smoothed per-bar (fast attack, soft
decay) for a fluid, musical motion.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
from typing import List, Optional

_N = 128                 # internal bar resolution; edges resample from this
_MAX = 1000              # cava ascii_max_range


def cava_available() -> bool:
    return shutil.which("cava") is not None


_CONFIG = f"""\
[general]
bars = {_N}
framerate = 60
autosens = 1
sensitivity = 130
[output]
method = raw
raw_target = /dev/stdout
data_format = ascii
ascii_max_range = {_MAX}
channels = mono
mono_option = average
bar_delimiter = 59
[smoothing]
noise_reduction = 0.30
"""


class Spectrum:
    """Live audio spectrum. ``bars(n)`` returns *n* values in 0..1, or None."""

    def __init__(self, attack: float = 0.85, decay: float = 0.34) -> None:
        self._attack = attack       # snap up fast
        self._decay = decay         # fall a little softer (musical gravity)
        self._peak = 0.15           # decaying reference level for auto-gain
        self._vals: List[float] = [0.0] * _N
        self._smooth: List[float] = [0.0] * _N
        self._proc: Optional[subprocess.Popen] = None
        self._ok = False
        self._lock = threading.Lock()
        self._cfg_path: Optional[str] = None
        if cava_available():
            self._start()

    def _start(self) -> None:
        try:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".conf", delete=False, prefix="lyricsooo-cava-"
            ) as f:
                f.write(_CONFIG)
                self._cfg_path = f.name
            self._proc = subprocess.Popen(
                ["cava", "-p", self._cfg_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            self._ok = True
            threading.Thread(target=self._reader, daemon=True).start()
        except Exception:
            self._ok = False

    def _reader(self) -> None:
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            line = line.strip().rstrip(";")
            if not line:
                continue
            try:
                parts = line.split(";")
                vals = [min(1.0, int(p) / _MAX) for p in parts if p != ""]
            except ValueError:
                continue
            if vals:
                with self._lock:
                    self._vals = vals

    def _tick_smooth(self) -> List[float]:
        """Advance the per-bar envelope one step toward the latest raw values."""
        with self._lock:
            raw = self._vals
        n = len(raw)
        if len(self._smooth) != n:
            self._smooth = list(raw)
        s = self._smooth
        a, d = self._attack, self._decay
        for i in range(n):
            target = raw[i]
            k = a if target > s[i] else d      # snap up, ease down
            s[i] += (target - s[i]) * k
        return s

    def bars(self, n: int) -> Optional[List[float]]:
        """Latest spectrum resampled to *n* values in 0..1, or None if unavailable."""
        if not self._ok or n <= 0:
            return None
        s = self._tick_smooth()
        m = len(s)
        if m == 0:
            return [0.0] * n
        if n == m:
            out = list(s)
        else:
            out = []
            for i in range(n):
                x = i * (m - 1) / (n - 1) if n > 1 else 0.0
                lo = int(x)
                hi = min(lo + 1, m - 1)
                out.append(s[lo] + (s[hi] - s[lo]) * (x - lo))

        # Auto-gain: normalise against a slowly-decaying peak so quiet passages
        # still fill out, then a perceptual curve to lift the low end. cava's raw
        # levels sit low; without this the bars barely twitch.
        peak = max(out) if out else 0.0
        self._peak = max(0.06, peak, self._peak * 0.985)
        g = self._peak
        return [min(1.0, (v / g) ** 0.72) for v in out]

    def close(self) -> None:
        self._ok = False
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=0.5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        if self._cfg_path:
            try:
                import os
                os.unlink(self._cfg_path)
            except Exception:
                pass
