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

_ESC = "\033["
_RESET = "\033[0m"

_FIELDS = [
    ("effect", ["Typewriter", "Standard"],
     "how each line appears — revealed char-by-char, or all at once"),
    ("style", ["Phrase", "Word"],
     "timing granularity — whole lines, or word-by-word (.wlrc)"),
]


def _accent(rgb) -> str:
    return f"{_ESC}38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


_ARROWS = {b"[A": "up", b"[B": "down", b"[C": "right", b"[D": "left",
           b"OA": "up", b"OB": "down", b"OC": "right", b"OD": "left"}
_KEYS = {b"\r": "enter", b"\n": "enter", b" ": "right",
         b"\t": "down", b"k": "up", b"j": "down", b"h": "left", b"l": "right",
         b"K": "up", b"J": "down", b"H": "left", b"L": "right",
         b"q": "esc", b"Q": "esc", b"\x03": "esc"}


def _decode_key(data: bytes) -> str:
    """Map a raw keypress (possibly a multi-byte escape sequence) to a key name."""
    if not data:
        return ""
    if data[:1] == b"\x1b":
        # ESC [ A  (or the ESC O A "application cursor" variant some terminals send)
        return _ARROWS.get(data[1:3], "esc")
    return _KEYS.get(data[:1], "")


def _read_key(fd: int) -> str:
    """Read one keypress off the raw fd. Reading bytes directly (not via the
    buffered ``sys.stdin``) is what makes arrow keys work: the whole ``ESC [ A``
    sequence is delivered in a single ``os.read`` instead of getting split with
    the tail stuck in Python's stream buffer where ``select`` can't see it."""
    import select

    data = os.read(fd, 8)
    # If only the lone ESC arrived, give the sequence tail a beat to land.
    if data == b"\x1b" and select.select([fd], [], [], 0.03)[0]:
        data += os.read(fd, 8)
    return _decode_key(data)


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


def choose(accent=(219, 199, 102), typewriter=True, wlrc=False) -> Optional[dict]:
    """Show the picker; return {'typewriter': bool, 'wlrc': bool} or defaults.

    Cancelling (q/esc) or no TTY returns the given defaults rather than None, so
    callers can always rely on a usable result.
    """
    defaults = {"typewriter": typewriter, "wlrc": wlrc}
    try:
        fd = sys.stdin.fileno()
        tty_ok = os.isatty(fd) and os.isatty(sys.stdout.fileno())
    except Exception:
        tty_ok = False
    if not tty_ok:
        return defaults

    import termios
    import tty

    acc = _accent(accent)
    sel = [0 if typewriter else 1, 1 if wlrc else 0]
    cursor = 0
    old = termios.tcgetattr(fd)
    out = sys.stdout
    out.write("\033[?25l\033[2J")
    try:
        tty.setcbreak(fd)
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
                return {"typewriter": sel[0] == 0, "wlrc": sel[1] == 1}
            elif key == "esc":
                return defaults
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        out.write(_RESET + "\033[?25h\033[2J\033[H")
        out.flush()


def _termsize():
    try:
        s = os.get_terminal_size()
        return s.columns, s.lines
    except Exception:
        return 80, 24
