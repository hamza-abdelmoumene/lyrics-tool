"""
Display utilities for LRC visualizer
Handles rendering text in various styles to terminal
"""
import sys
import os
from typing import List


# Diff-render state: skip redraws when the frame is unchanged, and cache
# expensive block-letter renders keyed by (text, terminal-size).
_render_cache = {}
_RENDER_CACHE_MAX = 512
_last_frame = None
_last_size = None


def get_terminal_size() -> tuple:
    """
    Get terminal dimensions.
    
    Returns:
        Tuple of (columns, rows)
    """
    try:
        size = os.get_terminal_size()
        return size.columns, size.lines
    except Exception:
        return 80, 24  # Default fallback


def clear_screen():
    """Clear the terminal screen"""
    global _last_frame
    sys.stdout.write('\033[2J\033[H')
    sys.stdout.flush()
    _last_frame = None


def hide_cursor():
    """Hide terminal cursor"""
    sys.stdout.write('\033[?25l')
    sys.stdout.flush()


def show_cursor():
    """Show terminal cursor"""
    sys.stdout.write('\033[?25h')
    sys.stdout.flush()


def _render_block_line(words: List[str], font_data: dict, height: int) -> List[str]:
    """Render a list of words as a single row of block letters (joined by spaces)."""
    lines = ['' for _ in range(height)]
    space_glyph = font_data.get(' ', ['    '] * height)
    space_width = len(space_glyph[0])

    for wi, word in enumerate(words):
        if wi > 0:
            for i in range(height):
                lines[i] += ' ' * (space_width + 1)
        for char in word.upper():
            glyph = font_data.get(char)
            if glyph is None:
                for i in range(height):
                    lines[i] += ' ' * (space_width + 1)
                continue
            for i in range(height):
                cell = glyph[i] if i < len(glyph) else ' ' * len(glyph[0])
                lines[i] += cell + ' '
    return lines


def _center_block(block_lines: List[str], cols: int, rows: int) -> str:
    """Vertically + horizontally center pre-rendered lines into a cols x rows frame."""
    block_lines = block_lines[:rows]
    pad_top = max(0, (rows - len(block_lines)) // 2)
    output = []
    for i in range(rows):
        if pad_top <= i < pad_top + len(block_lines):
            line = block_lines[i - pad_top]
            pad_left = max(0, (cols - len(line)) // 2)
            output.append((' ' * pad_left + line).ljust(cols)[:cols])
        else:
            output.append(' ' * cols)
    return '\n'.join(output)


def render_block_text(text: str, font_data: dict) -> str:
    """
    Render text using block letters, adapting to the terminal size.

    Wraps the phrase across multiple block-letter rows so it fits the current
    width, and falls back to plain centered text when block letters cannot fit
    (terminal too narrow for a single word, or too short for the stacked rows).

    Args:
        text: Text to render
        font_data: Font dictionary mapping characters to line arrays

    Returns:
        Rendered text as string sized to the current terminal
    """
    cols, rows = get_terminal_size()
    key = ('block', text, cols, rows)
    cached = _render_cache.get(key)
    if cached is not None:
        return cached

    height = len(font_data.get('A', ['']))
    words = text.upper().split() or ['']

    # Greedily pack words into rows whose rendered width fits the terminal.
    row_words: List[List[str]] = []
    current: List[str] = []
    for word in words:
        trial = current + [word]
        trial_w = max(len(l) for l in _render_block_line(trial, font_data, height))
        if current and trial_w > cols:
            row_words.append(current)
            current = [word]
        else:
            current = trial
    if current:
        row_words.append(current)

    # Stack the rendered rows with a blank separator line between them.
    block_lines: List[str] = []
    for idx, rw in enumerate(row_words):
        if idx > 0:
            block_lines.append('')
        block_lines.extend(_render_block_line(rw, font_data, height))

    max_width = max((len(l) for l in block_lines), default=0)

    # Block letters still don't fit (a single word too wide, or too many rows):
    # degrade gracefully to wrapped plain text rather than clipping.
    if max_width > cols or len(block_lines) > rows:
        import textwrap
        wrapped = textwrap.wrap(text, width=max(1, cols)) or ['']
        frame = _center_block(wrapped, cols, rows)
    else:
        frame = _center_block(block_lines, cols, rows)

    if len(_render_cache) >= _RENDER_CACHE_MAX:
        _render_cache.clear()
    _render_cache[key] = frame
    return frame


def render_simple_text(text: str, centered: bool = True) -> str:
    """
    Render text in simple format (no block letters).
    
    Args:
        text: Text to render
        centered: Whether to center the text
        
    Returns:
        Rendered text as string
    """
    cols, rows = get_terminal_size()
    
    if centered:
        pad_top = rows // 2
        pad_left = max(0, (cols - len(text)) // 2)
        
        output = []
        for i in range(rows):
            if i == pad_top:
                output.append((' ' * pad_left + text).ljust(cols)[:cols])
            else:
                output.append(' ' * cols)

        return '\n'.join(output)
    else:
        return text


def render_waiting() -> str:
    """
    Render waiting/loading indicator.
    
    Returns:
        Rendered waiting text
    """
    return render_simple_text("•••", centered=True)


def _paint(frame: str, clear: bool):
    """Write a full-screen frame, diffing against the last paint.

    Skips the write entirely when nothing changed (no flicker, no CPU). Repaints
    from the home position instead of clearing the whole screen, except on an
    explicit clear or a terminal resize, where a one-shot clear avoids artifacts.
    """
    global _last_frame, _last_size
    size = get_terminal_size()
    resized = size != _last_size
    _last_size = size

    if frame == _last_frame and not clear and not resized:
        return

    prefix = '\033[2J\033[H' if (clear or resized) else '\033[H'
    sys.stdout.write(prefix + frame)
    sys.stdout.flush()
    _last_frame = frame


def display_text(text: str, use_block_letters: bool = True, font_data: dict = None, clear: bool = False):
    """
    Display text in the terminal (diffed; only repaints on change/resize).

    Args:
        text: Text to display
        use_block_letters: Whether to use block letter rendering
        font_data: Font to use for block letters
        clear: Force a full clear before painting
    """
    if use_block_letters and font_data:
        frame = render_block_text(text, font_data)
    else:
        frame = render_simple_text(text)
    _paint(frame, clear)


def display_waiting(clear: bool = True):
    """
    Display waiting indicator.

    Args:
        clear: Force a full clear before painting
    """
    _paint(render_waiting(), clear)
