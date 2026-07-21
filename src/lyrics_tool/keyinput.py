"""Cross-platform terminal key input for the visualizer and the picker.

Two consumers share this module:

* the running visualizer wants **non-blocking single keystrokes** for the live
  sync nudges (``-`` / ``+`` / ``,`` / ``.`` / ``0``) — see :class:`KeyReader`;
* the ``--select`` picker wants a **blocking, semantic** read that understands
  arrow keys — see :func:`read_key`.

POSIX uses ``termios``/``tty`` (cbreak) with ``select`` and raw ``os.read`` so
arrow escape sequences arrive intact; Windows uses ``msvcrt``. Neither path
imports the other's modules, and everything is a safe no-op when stdin isn't an
interactive terminal (tests, pipes), so the tools never hang. :func:`enable_ansi`
switches the Windows console into VT mode so the ANSI-based renderer shows
colour there too.
"""
from __future__ import annotations

import os
import sys
from typing import Optional

IS_WINDOWS = sys.platform == "win32"


def stdin_is_tty() -> bool:
    """True only when both stdin and stdout are interactive terminals."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def enable_ansi() -> None:
    """Enable ANSI/VT processing on the Windows console (no-op elsewhere).

    Modern Windows Terminal has this on already; classic conhost needs the
    ``ENABLE_VIRTUAL_TERMINAL_PROCESSING`` flag set or the renderer's colour
    escapes print as literal text. Failures are swallowed — worst case, colour.
    """
    if not IS_WINDOWS:
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]  # Windows-only
        for handle_id in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            handle = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


# ── semantic key names (used by the picker) ──────────────────────────────────

_ARROWS = {b"[A": "up", b"[B": "down", b"[C": "right", b"[D": "left",
           b"OA": "up", b"OB": "down", b"OC": "right", b"OD": "left"}
_KEYS = {b"\r": "enter", b"\n": "enter", b" ": "right",
         b"\t": "down", b"k": "up", b"j": "down", b"h": "left", b"l": "right",
         b"K": "up", b"J": "down", b"H": "left", b"L": "right",
         b"q": "esc", b"Q": "esc", b"\x03": "esc"}
# Windows delivers arrows as a 0x00/0xe0 prefix then a scan code.
_WIN_ARROWS = {b"H": "up", b"P": "down", b"M": "right", b"K": "left"}


def decode_key(data: bytes) -> str:
    """Map a raw keypress (possibly a multi-byte escape sequence) to a key name."""
    if not data:
        return ""
    if data[:1] == b"\x1b":
        # ESC [ A  (or the ESC O A "application cursor" variant some terminals send)
        return _ARROWS.get(data[1:3], "esc")
    return _KEYS.get(data[:1], "")


def read_key(fd: int) -> str:
    """Block for one keypress; return a name (up/down/left/right/enter/esc/'').

    On POSIX the whole ``ESC [ A`` sequence is read in a single ``os.read`` so
    the arrow tail never gets stuck in a stream buffer where ``select`` can't
    see it. On Windows the ``msvcrt`` two-byte arrow encoding is decoded.
    """
    if IS_WINDOWS:
        import msvcrt  # Windows-only stdlib; guarded by IS_WINDOWS

        ch = msvcrt.getwch()  # type: ignore[attr-defined]
        if ch in ("\x00", "\xe0"):  # arrow / function-key prefix
            code = msvcrt.getwch().encode("latin-1", "ignore")  # type: ignore[attr-defined]
            return _WIN_ARROWS.get(code, "")
        return _KEYS.get(ch.encode("latin-1", "ignore")[:1], "")

    import select

    data = os.read(fd, 8)
    # If only the lone ESC arrived, give the sequence tail a beat to land.
    if data == b"\x1b" and select.select([fd], [], [], 0.03)[0]:
        data += os.read(fd, 8)
    return decode_key(data)


class raw_mode:
    """Context manager putting a POSIX terminal into cbreak mode (no-op on Windows).

    ``msvcrt`` reads the console directly without a mode switch, so on Windows
    this does nothing. On POSIX it restores the previous settings on exit no
    matter how the block ends.
    """

    def __init__(self, fd: int) -> None:
        self._fd = fd
        self._old: Optional[list] = None

    def __enter__(self) -> "raw_mode":
        if not IS_WINDOWS:
            import termios
            import tty

            self._old = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        return self

    def __exit__(self, *exc):
        if self._old is not None:
            import termios

            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)
        return False


class KeyReader:
    """Non-blocking single-keystroke reader; a no-op unless stdin is a TTY.

    Lets the running visualizer accept live sync nudges without a blocking
    prompt. Restores the terminal on exit no matter how the loop ends. Safe
    under tests / pipes: when stdin isn't interactive every method does nothing.
    """

    def __init__(self) -> None:
        self._active = False
        self._fd: Optional[int] = None
        self._old: Optional[list] = None

    def __enter__(self) -> "KeyReader":
        if not stdin_is_tty():
            return self
        if IS_WINDOWS:
            self._active = True
            return self
        try:
            import termios
            import tty

            self._fd = sys.stdin.fileno()
            self._old = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
            self._active = True
        except Exception:
            self._active = False
        return self

    def get(self) -> Optional[str]:
        """Return one pending keystroke, or ``None`` if none is waiting."""
        if not self._active:
            return None
        try:
            if IS_WINDOWS:
                import msvcrt  # Windows-only stdlib; guarded by IS_WINDOWS

                if msvcrt.kbhit():  # type: ignore[attr-defined]
                    ch = msvcrt.getwch()  # type: ignore[attr-defined]
                    if ch in ("\x00", "\xe0"):  # swallow arrow scan codes here
                        msvcrt.getwch()  # type: ignore[attr-defined]
                        return None
                    return ch
                return None

            import select

            if select.select([sys.stdin], [], [], 0)[0]:
                return sys.stdin.read(1)
        except Exception:
            return None
        return None

    def __exit__(self, *exc):
        if self._old is not None:
            try:
                import termios

                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)
            except Exception:
                pass
        return False
