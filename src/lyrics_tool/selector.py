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


def _read_key() -> str:
    """Return a normalised key name from one keypress (raw mode assumed)."""
    ch = sys.stdin.read(1)
    if ch == "\x1b":                       # escape or arrow sequence
        seq = sys.stdin.read(2) if _kbhit() else ""
        return {"[A": "up", "[B": "down", "[C": "right", "[D": "left"}.get(seq, "esc")
    return {
        "\r": "enter", "\n": "enter", " ": "right",
        "k": "up", "j": "down", "h": "left", "l": "right",
        "q": "esc", "\x03": "esc",
    }.get(ch, "")


def _kbhit() -> bool:
    import select
    return bool(select.select([sys.stdin], [], [], 0.0)[0])


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
            key = _read_key()
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
