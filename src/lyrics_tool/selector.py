"""
A small interactive picker shown before the visualiser starts.

Two choices — the reveal **effect** (typewriter / standard) and the lyric
**style** (phrase / word) — on a centred, theme-tinted card driven entirely by
the keyboard. It's optional: without a TTY (piped, scripted) it just returns the
defaults, so nothing ever hangs.

    ↑↓ / jk   move between rows
    ←→ / hl   change the option
    ⏎ / space start
    q / esc   cancel (use defaults)
"""
from __future__ import annotations

import os
import sys
from typing import Optional

from .keyinput import decode_key as _decode_key  # noqa: F401 (kept as a stable alias)
from .keyinput import raw_mode
from .keyinput import read_key as _read_key

_ESC = "\033["
_RESET = "\033[0m"

# The reveal effect names, in the same order as the "effect" chips below.
_REVEALS = ["standard", "typewriter", "fade", "glow"]

_FIELDS = [
    ("effect", ["Standard", "Typewriter", "Fade", "Glow"],
     "how each line appears — instant, typed out, softly faded in, or breathing"),
    ("style", ["Phrase", "Word"],
     "timing granularity — whole lines, or word-by-word (.wlrc)"),
]


def _accent(rgb) -> str:
    return f"{_ESC}38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


# Key reading (arrow-aware, cross-platform) lives in ``keyinput``; ``_decode_key``
# and ``_read_key`` above are stable aliases into it.


def _render(fields, sel, cursor, accent: str, cols: int, rows: int) -> str:
    dim = f"{_ESC}2m"
    bold = f"{_ESC}1m"
    inner_w = 46
    lines = []
    lines.append(f"{accent}{bold}∇ lyricsooo{_RESET}{dim}  ·  set the mood{_RESET}")
    lines.append("")
    for fi, (label, opts, hint) in enumerate(fields):
        active = fi == cursor
        marker = f"{accent}▸{_RESET} " if active else "  "
        row = f"{marker}{label:<8} "
        chips = []
        for oi, opt in enumerate(opts):
            if oi == sel[fi]:
                chips.append(f"{accent}{bold}[ {opt} ]{_RESET}")
            else:
                chips.append(f"{dim}  {opt}  {_RESET}")
        row += " ".join(chips)
        lines.append(row)
        if active:
            lines.append(f"    {dim}{hint}{_RESET}")
        else:
            lines.append("")
    lines.append("")
    lines.append(f"{dim}↑↓ row   ←→ change   ⏎ start   q defaults{_RESET}")

    # centre the block
    pad_top = max(0, (rows - len(lines)) // 2)
    pad = max(0, (cols - inner_w) // 2)
    out = [""] * pad_top
    for ln in lines:
        out.append(" " * pad + ln)
    return "\n".join(out)


def choose(accent=(219, 199, 102), reveal="standard", wlrc=False) -> Optional[dict]:
    """Show the picker; return {'reveal': str, 'wlrc': bool} or defaults.

    ``reveal`` is one of :data:`_REVEALS`. Cancelling (q/esc) or no TTY returns
    the given defaults rather than None, so callers can always rely on a result.
    """
    defaults = {"reveal": reveal, "wlrc": wlrc}
    try:
        fd = sys.stdin.fileno()
        tty_ok = os.isatty(fd) and os.isatty(sys.stdout.fileno())
    except Exception:
        tty_ok = False
    if not tty_ok:
        return defaults

    acc = _accent(accent)
    reveal_idx = _REVEALS.index(reveal) if reveal in _REVEALS else 0
    sel = [reveal_idx, 1 if wlrc else 0]
    cursor = 0
    out = sys.stdout
    out.write("\033[?25l\033[2J")
    try:
        with raw_mode(fd):
            while True:
                cols, rows = _termsize()
                out.write("\033[H" + _render(_FIELDS, sel, cursor, acc, cols, rows) + _RESET)
                out.flush()
                key = _read_key(fd)
                if key == "up":
                    cursor = (cursor - 1) % len(_FIELDS)
                elif key == "down":
                    cursor = (cursor + 1) % len(_FIELDS)
                elif key in ("left", "right"):
                    n = len(_FIELDS[cursor][1])
                    sel[cursor] = (sel[cursor] + (1 if key == "right" else -1)) % n
                elif key == "enter":
                    return {"reveal": _REVEALS[sel[0]], "wlrc": sel[1] == 1}
                elif key == "esc":
                    return defaults
    finally:
        out.write(_RESET + "\033[?25h\033[2J\033[H")
        out.flush()


def _termsize():
    try:
        s = os.get_terminal_size()
        return s.columns, s.lines
    except Exception:
        return 80, 24
