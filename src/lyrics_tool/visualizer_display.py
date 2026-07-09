"""
Display utilities for LRC visualizer
Handles rendering text in various styles to terminal
"""
import sys
import os
import time
import random
from typing import List, Optional, Tuple

RGB = Tuple[int, int, int]
_RESET = '\033[0m'
# Dim, neutral grey for the ambient notes so they read as background, never
# competing with the lyric. 256-colour code keeps it terminal-friendly. A note
# may carry its own grey shade (depth/twinkle); this is the fallback.
_NOTE_GREY = 240
_NOTE_SGR = f'\033[38;5;{_NOTE_GREY}m'


def _note_sgr(shade: int) -> str:
    """SGR for a note painted in 256-colour grey ``shade`` (dim → soft)."""
    return f'\033[38;5;{shade}m'

# Glyphs the track-switch glitch burst scrambles letters into. A mix of block
# shading + symbols reads as digital corruption without breaking column width.
_GLITCH_GLYPHS = '▓▒░█▌▐#@%&$*!?/\\|=+<>'

# Braille spinner cycled by the waiting / searching screens. Every glyph is a
# single cell wide, so the centered frame never shifts as it spins.
_SPINNER = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'

# Bored faces the ad-break screen cycles through (held a few ticks each), with a
# drifting snooze trail beside them — turns a static card into a little "waiting
# it out" loop. All glyphs are narrow BMP characters so column width is stable.
_AD_FACES = ['( -_- )', '( ¬_¬ )', '( ˘_˘ )', '( =_= )', '( ·_· )']
_AD_SNOOZE = ['z   ', 'zZ  ', 'zZz ', ' zZz', '  zZ', '   z']


# Diff-render state: skip redraws when the frame is unchanged, and cache
# expensive block-letter renders keyed by (text, terminal-size).
_render_cache = {}
_RENDER_CACHE_MAX = 512
_last_frame = None
_last_size = None


# ── reactive spectrum border ────────────────────────────────────────────────
# An optional cava-driven equaliser framing the lyrics on all four edges. The
# trick that keeps it non-invasive: when a border is active, get_terminal_size()
# reports the *inner* box, so every renderer (lyrics, cards, idle screens)
# centres itself inside the frame with zero changes — and _paint() draws the
# spectrum ring around the inner frame at paint time.
_BORDER_ON = False
_BORDER = {"spectrum": None, "color": (220, 200, 120)}
_MY = 4   # top/bottom band thickness in character rows  (×8 eighth-block levels)
_MX = 7   # left/right band thickness in character cols   (×8 eighth-block levels)


def _real_size() -> tuple:
    try:
        s = os.get_terminal_size()
        return s.columns, s.lines
    except Exception:
        return 80, 24


def _border_active() -> bool:
    """Border on *and* the terminal is big enough to hold it comfortably."""
    if not _BORDER_ON:
        return False
    c, r = _real_size()
    return c >= 2 * _MX + 16 and r >= 2 * _MY + 6


def get_terminal_size() -> tuple:
    """Terminal size — the *inner* box when a spectrum border is active."""
    c, r = _real_size()
    if _border_active():
        return c - 2 * _MX, r - 2 * _MY
    return c, r


def enable_border(spectrum, color: RGB) -> None:
    """Turn on the reactive spectrum frame, driven by ``spectrum`` (see spectrum.py)."""
    global _BORDER_ON, _last_frame
    _BORDER["spectrum"] = spectrum
    _BORDER["color"] = color
    _BORDER_ON = True
    _last_frame = None


def set_border_color(color: RGB) -> None:
    if color is not None:
        _BORDER["color"] = color


def disable_border() -> None:
    global _BORDER_ON, _last_frame
    _BORDER_ON = False
    _BORDER["spectrum"] = None
    _last_frame = None


def border_enabled() -> bool:
    return _BORDER_ON


def _resample(arr, n: int):
    m = len(arr)
    if n <= 0 or m == 0:
        return [0.0] * max(0, n)
    if n == m:
        return list(arr)
    out = []
    for i in range(n):
        x = i * (m - 1) / (n - 1) if n > 1 else 0.0
        lo = int(x)
        hi = min(lo + 1, m - 1)
        out.append(arr[lo] + (arr[hi] - arr[lo]) * (x - lo))
    return out


def _grad(color: RGB, t: float) -> RGB:
    """Bar colour at height ``t`` (0 baseline → 1 tip): dim base → bright toward the tip."""
    r, g, b = color
    t = max(0.0, min(1.0, t))
    dim = (r * 0.5, g * 0.5, b * 0.5)                              # saturated base
    hot = (r + (255 - r) * 0.7, g + (255 - g) * 0.7, b + (255 - b) * 0.7)  # near-white tips
    return tuple(int(dim[i] + (hot[i] - dim[i]) * t) for i in range(3))


# Eighth-block ramps → 8 sub-levels per cell, so a 4-cell band shows 32 steps of
# bar height. Vertical fills from the bottom, horizontal from the left.
_EIGHTHS_V = " ▁▂▃▄▅▆▇█"
_EIGHTHS_H = " ▏▎▍▌▋▊▉█"


def _bar_cells(value: float, n: int, color: RGB, reverse: bool, glyphs) -> List[str]:
    """Render one bar as ``n`` cell-strings, index 0 = the outer (baseline) cell.

    ``reverse`` flips the partial to fill from the far side of the cell (used for
    the top and right edges, whose bars grow away from a bottom/left-anchored
    glyph), painted as background so the ink lands on the correct side.
    """
    total = max(0.0, min(1.0, value)) * n * 8.0     # height in eighths
    cells = []
    for pos in range(n):
        filled = total - pos * 8.0
        t = (pos + 0.6) / n                          # colour: dim base → bright tip
        r, g, b = _grad(color, t)
        if filled <= 0.0:
            cells.append(" ")
        elif filled >= 8.0:
            cells.append(f"\033[38;2;{r};{g};{b}m{glyphs[8]}{_RESET}")
        else:
            e = max(1, min(7, int(filled)))
            if not reverse:
                cells.append(f"\033[38;2;{r};{g};{b}m{glyphs[e]}{_RESET}")
            else:
                # far-side partial: paint the cell bg with the bar colour and let
                # the (8-e) glyph's ink cover the empty side in the default colour.
                cells.append(f"\033[38;2;0;0;0m\033[48;2;{r};{g};{b}m{glyphs[8 - e]}{_RESET}")
    return cells


def _v_band(values, my: int, color: RGB, anchor: str) -> List[str]:
    """A horizontal spectrum strip of vertical bars → ``my`` screen rows (top→bottom)."""
    reverse = anchor == "top"
    per_col = [_bar_cells(v, my, color, reverse, _EIGHTHS_V) for v in values]
    # index 0 is the outer cell: top edge's outer is the top row; bottom's is the
    # bottom row, so flip its per-column order into screen order.
    if anchor == "bottom":
        per_col = [list(reversed(c)) for c in per_col]
    return ["".join(col[j] for col in per_col) for j in range(my)]


def _h_band(values, mx: int, color: RGB, anchor: str) -> List[str]:
    """A vertical spectrum strip of horizontal bars → one ``mx``-wide cell per row."""
    reverse = anchor == "right"
    out = []
    for v in values:
        cells = _bar_cells(v, mx, color, reverse, _EIGHTHS_H)   # index 0 = outer
        if anchor == "right":                                   # outer is the right col
            cells = list(reversed(cells))
        out.append("".join(cells))
    return out


def _frame_with_border(inner: str, real_cols: int, real_rows: int) -> str:
    """Wrap an inner (inset-sized) frame in a live spectrum ring."""
    mx, my = _MX, _MY
    iw, ih = real_cols - 2 * mx, real_rows - 2 * my
    color = _BORDER["color"]
    spec = _BORDER["spectrum"]
    base = spec.bars(128) if spec is not None else None
    if not base:
        base = [0.0] * 128

    top = _resample(base, iw)
    bottom = list(reversed(top))                 # mirror for rotational symmetry
    left = _resample(base, ih)
    right = list(reversed(left))

    top_band = _v_band(top, my, color, "top")
    bot_band = _v_band(bottom, my, color, "bottom")
    left_col = _h_band(left, mx, color, "left")
    right_col = _h_band(right, mx, color, "right")

    inner_lines = inner.split("\n")
    corner = " " * mx
    out = [corner + top_band[j] + corner for j in range(my)]
    for r in range(ih):
        line = inner_lines[r] if r < len(inner_lines) else " " * iw
        out.append(left_col[r] + line + right_col[r])
    out += [corner + bot_band[j] + corner for j in range(my)]
    return "\n".join(out)


def clear_screen():
    """Clear the terminal screen (and reset any lingering colour)."""
    global _last_frame
    sys.stdout.write(_RESET + '\033[2J\033[H')
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


def _pack_block_lines(text: str, font_data: dict, cols: int) -> tuple:
    """Render text into stacked block-letter rows that fit ``cols`` wide.

    Returns (block_lines, max_width). Words are greedily packed into rows and
    rows stacked with a blank separator between them.
    """
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
    return block_lines, max_width


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

    block_lines, max_width = _pack_block_lines(text, font_data, cols)

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


def render_now_playing(artist: str, title: str, font_data: dict) -> str:
    """Render a full-screen 'now playing' card: title in block letters with the
    artist on a plain centered line beneath it."""
    cols, rows = get_terminal_size()

    if font_data:
        block_lines, max_width = _pack_block_lines(title, font_data, cols)
        if max_width > cols or len(block_lines) + 2 > rows:
            import textwrap
            block_lines = textwrap.wrap(title.upper(), width=max(1, cols)) or ['']
    else:
        block_lines = [title.upper()]

    artist_line = artist.strip()
    if artist_line:
        if len(artist_line) > cols:
            artist_line = artist_line[:cols]
        block_lines = block_lines + ['', artist_line]

    return _center_block(block_lines, cols, rows)


def _tint_frame(frame: str, bg: RGB, fg: RGB) -> str:
    """Paint every row of a frame on a solid ``bg`` with ``fg`` text.

    Each row is already padded to the full width, so wrapping it in a
    background-colour SGR fills the whole screen with the cover's colour.
    """
    br, bgc, bb = bg
    fr, fgc, fb = fg
    sgr = f'\033[48;2;{br};{bgc};{bb}m\033[38;2;{fr};{fgc};{fb}m'
    return '\n'.join(f'{sgr}{row}{_RESET}' for row in frame.split('\n'))


def _overlay_notes(frame: str, notes: List[Tuple[int, int, str]]) -> str:
    """Stamp dim music-note glyphs onto the blank cells of ``frame``.

    Notes are only placed on spaces, so they drift *behind* the lyric letters
    and never obscure them. Each glyph is wrapped in colour codes but stays one
    cell wide, keeping the frame's column alignment intact.
    """
    if not notes:
        return frame
    grid = [list(row) for row in frame.split('\n')]
    for note in notes:
        row, col, glyph = note[0], note[1], note[2]
        shade = note[3] if len(note) > 3 else _NOTE_GREY
        if 0 <= row < len(grid) and 0 <= col < len(grid[row]) and grid[row][col] == ' ':
            grid[row][col] = f'{_note_sgr(shade)}{glyph}{_RESET}'
    return '\n'.join(''.join(row) for row in grid)


def _jitter_color(rgb: RGB, amount: float) -> RGB:
    """Randomly nudge each channel by up to ``amount`` for a chromatic flicker."""
    j = int(40 * amount)
    if j <= 0:
        return rgb
    return tuple(max(0, min(255, c + random.randint(-j, j))) for c in rgb)


# Hot flicker colours the glitch flashes between for a chromatic-aberration feel.
_GLITCH_HOT = [(255, 40, 90), (40, 220, 255), (255, 255, 255), (180, 60, 255)]


def _glitch_frame(frame: str, cols: int, amount: float) -> str:
    """Corrupt a frame for the track-switch glitch burst.

    ``amount`` (1→0) scales how violent the corruption is. Three layered effects:
    horizontal *band tears* (contiguous row groups slip sideways), per-letter
    *scramble* into :data:`_GLITCH_GLYPHS`, and occasional whole-row *dropouts*.
    Every row is re-padded to exactly ``cols`` so the tint/overwrite stays aligned.
    """
    lines = frame.split('\n')
    n = len(lines)

    # Band tears: shift a few contiguous bands of rows by a chunky offset.
    for _ in range(int(amount * 3) + 1):
        if random.random() >= amount:
            continue
        h = random.randint(1, max(1, n // 4))
        top = random.randint(0, max(0, n - h))
        shift = random.randint(-10, 10)
        for i in range(top, top + h):
            ln = lines[i]
            if shift > 0:
                ln = ' ' * shift + ln
            elif shift < 0:
                ln = ln[-shift:]
            lines[i] = ln

    out: List[str] = []
    for line in lines:
        if line.strip():
            if random.random() < amount * 0.12:        # whole-row dropout
                line = ''
            else:                                       # per-letter scramble
                chars = list(line)
                for i, c in enumerate(chars):
                    if c != ' ' and random.random() < amount * 0.32:
                        chars[i] = random.choice(_GLITCH_GLYPHS)
                line = ''.join(chars)
        out.append(line.ljust(cols)[:cols])
    return '\n'.join(out)


def _glitch_tint(frame: str, bg: Optional[RGB], fg: Optional[RGB], amount: float) -> str:
    """Colour a corrupted glitch frame, flickering rows toward hot accent colours.

    With a cover (``bg``/``fg`` set) each row is filled with the tinted background
    and its text either jittered ``fg`` or, with probability scaling on
    ``amount``, a hot flicker colour. Without a cover the text alone flickers on
    the default background.
    """
    out: List[str] = []
    for row in frame.split('\n'):
        if random.random() < amount * 0.45:
            fr, fgc, fb = random.choice(_GLITCH_HOT)
        elif fg is not None:
            fr, fgc, fb = _jitter_color(fg, amount)
        else:
            out.append(row)                            # no cover, no flicker: plain
            continue
        fg_sgr = f'\033[38;2;{fr};{fgc};{fb}m'
        if bg is not None:
            br, bgc, bb = _jitter_color(bg, amount * 0.5)
            out.append(f'\033[48;2;{br};{bgc};{bb}m{fg_sgr}{row}{_RESET}')
        else:
            out.append(f'{fg_sgr}{row}{_RESET}')
    return '\n'.join(out)


def _compose_lyric(frame: str, notes, color: Optional[RGB]) -> str:
    """Paint a lyric frame: letters in ``color``, notes dim grey, spaces blank.

    Does notes and text-colour in a single pass over the plain frame so neither
    fights the other's escape codes — note glyphs only ever land on space cells,
    and the colour run is closed before/after them. Visible column width is
    preserved (each glyph/letter stays one cell wide).
    """
    note_map = {}
    if notes:
        for note in notes:
            r, c, g = note[0], note[1], note[2]
            shade = note[3] if len(note) > 3 else _NOTE_GREY
            note_map[(r, c)] = (g, shade)
    color_sgr = None
    if color is not None:
        cr, cg, cb = color
        color_sgr = f'\033[38;2;{cr};{cg};{cb}m'

    out_lines: List[str] = []
    for ri, row in enumerate(frame.split('\n')):
        parts: List[str] = []
        in_color = False
        for ci, ch in enumerate(row):
            note = note_map.get((ri, ci)) if note_map else None
            if note is not None and ch == ' ':
                if in_color:
                    parts.append(_RESET)
                    in_color = False
                glyph, shade = note
                parts.append(f'{_note_sgr(shade)}{glyph}{_RESET}')
            elif ch != ' ' and color_sgr is not None:
                if not in_color:
                    parts.append(color_sgr)
                    in_color = True
                parts.append(ch)
            else:
                if in_color:
                    parts.append(_RESET)
                    in_color = False
                parts.append(ch)
        if in_color:
            parts.append(_RESET)
        out_lines.append(''.join(parts))
    return '\n'.join(out_lines)


def _render_status(lines: List[str], notes=None, color: Optional[RGB] = None) -> str:
    """Center a stack of plain text lines into the terminal, with notes/colour.

    Shared by the ambient idle screens (waiting, searching, no-lyrics): each is
    just a few centered lines drifting over the same music notes as the lyrics,
    so the view never goes dead while we wait on the player or the network.
    """
    cols, rows = get_terminal_size()
    frame = _center_block(lines, cols, rows)
    if notes or color is not None:
        frame = _compose_lyric(frame, notes, color)
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


def display_searching(
    title: str,
    notes=None,
    color: Optional[RGB] = None,
    phase: int = 0,
):
    """Animated 'finding lyrics' screen shown while a track's lyrics download.

    A braille spinner over the song title, drifting on the ambient notes — keeps
    the view alive (and responsive to track switches) instead of freezing on the
    title card while the network call runs off-thread.
    """
    spin = _SPINNER[phase % len(_SPINNER)]
    lines = ['', f'{spin}  finding lyrics  {spin}', '', (title or '').strip(), '']
    _paint(_render_status(lines, notes, color), clear=False)


def display_no_lyrics(
    title: str,
    notes=None,
    color: Optional[RGB] = None,
):
    """Graceful idle screen for a track we couldn't find synced lyrics for.

    Replaces the old behaviour of freezing on the title card forever: the notes
    keep drifting and the loop keeps watching for the next track, so the app
    never *looks* stuck just because one song has no lyrics.
    """
    lines = [
        '♪   ·   ♫   ·   ♩',
        '',
        'no synced lyrics for',
        (title or '').strip(),
        '',
        'still listening — switch track anytime',
    ]
    _paint(_render_status(lines, notes, color), clear=False)


def _paint(frame: str, clear: bool):
    """Write a full-screen frame, diffing against the last paint.

    Skips the write entirely when nothing changed (no flicker, no CPU). Repaints
    from the home position instead of clearing the whole screen, except on an
    explicit clear or a terminal resize, where a one-shot clear avoids artifacts.
    """
    global _last_frame, _last_size
    real_cols, real_rows = _real_size()
    resized = (real_cols, real_rows) != _last_size
    _last_size = (real_cols, real_rows)

    # Wrap the (inner) frame in the live spectrum ring when the border is on.
    if _border_active():
        frame = _frame_with_border(frame, real_cols, real_rows)

    if frame == _last_frame and not clear and not resized:
        return

    # Lead every paint with a reset so a previous frame's colour (e.g. the
    # cover-tinted card) can never bleed into the next one (e.g. the lyrics).
    prefix = ('\033[2J\033[H' if (clear or resized) else '\033[H') + _RESET
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


def display_waiting(notes=None, phase: int = 0, clear: bool = False):
    """
    Display the 'waiting for a player' screen (animated spinner + notes).

    Args:
        notes: Iterable of (row, col, glyph) background notes, or None
        phase: Animation tick (advance once per call to spin the indicator)
        clear: Force a full clear before painting
    """
    spin = _SPINNER[phase % len(_SPINNER)]
    lines = [spin, '', 'waiting for a player', '', 'play something to begin']
    _paint(_render_status(lines, notes, None), clear)


def display_now_playing(
    artist: str,
    title: str,
    font_data: dict = None,
    bg: Optional[RGB] = None,
    fg: Optional[RGB] = None,
):
    """
    Display the now-playing card (track title + artist).

    Forces a full clear so the card cleanly replaces whatever lyrics were on
    screen for the previous track. When ``bg``/``fg`` are given (derived from
    the album cover), the whole card is tinted in that colour with readable
    text; otherwise it uses the default terminal colours.

    Args:
        artist: Artist name shown beneath the title
        title: Track title shown in block letters
        font_data: Font to use for block letters
        bg: Optional background RGB taken from the album cover
        fg: Optional foreground RGB (white on dark covers, dark on light ones)
    """
    frame = render_now_playing(artist, title, font_data)
    if bg is not None and fg is not None:
        frame = _tint_frame(frame, bg, fg)
    _paint(frame, clear=True)


def display_now_playing_glitch(
    artist: str,
    title: str,
    font_data: dict = None,
    bg: Optional[RGB] = None,
    fg: Optional[RGB] = None,
    frames: int = 8,
    frame_dt: float = 0.03,
):
    """Announce a track with a short glitch burst, then settle to the clean card.

    Paints ``frames`` decaying-corruption frames (band tears, letters scrambling,
    hot colour flicker) before resolving to the steady — optionally cover-tinted —
    now-playing card. Blocks for roughly ``frames * frame_dt`` seconds (~0.5s);
    the caller holds the settled card for the rest of its on-screen time.
    ``bg``/``fg`` tint exactly like :func:`display_now_playing`.
    """
    cols, _ = get_terminal_size()
    base = render_now_playing(artist, title, font_data)
    for k in range(frames):
        amount = 1.0 - (k / max(1, frames))      # 1 → ~0 over the burst
        g = _glitch_frame(base, cols, amount)
        g = _glitch_tint(g, bg, fg, amount)
        _paint(g, clear=(k == 0))                 # clear once, then repaint home
        time.sleep(frame_dt)
    frame = base
    if bg is not None and fg is not None:
        frame = _tint_frame(frame, bg, fg)
    _paint(frame, clear=False)


def render_ad_screen(font_data: dict = None, phase: int = 0) -> str:
    """Render the 'ad break' screen: 'AD' in block letters over a bored face.

    ``phase`` animates the card: the bored face changes every few ticks and a
    snooze trail (``z`` → ``zZz`` → drifting off) cycles beside it, so the wait
    reads as "dozing through the ad" rather than a frozen frame.
    """
    cols, rows = get_terminal_size()
    if font_data:
        block, max_width = _pack_block_lines('AD', font_data, cols)
        if max_width > cols or len(block) + 3 > rows:
            block = ['AD']
    else:
        block = ['AD']
    face = _AD_FACES[(phase // 4) % len(_AD_FACES)]
    snooze = _AD_SNOOZE[phase % len(_AD_SNOOZE)]
    lines = block + ['', f'{face}   {snooze}', '', 'ad break — back to the music soon']
    return _center_block(lines, cols, rows)


def display_ad(
    font_data: dict = None,
    phase: int = 0,
    notes=None,
    color: Optional[RGB] = None,
    clear: bool = False,
):
    """Show the animated bored 'ad break' screen while a Spotify advert plays.

    Advance ``phase`` once per call to animate the bored face and snooze trail;
    ``notes`` drift behind it just like on the lyric view.
    """
    frame = render_ad_screen(font_data, phase)
    if notes or color is not None:
        frame = _compose_lyric(frame, notes, color)
    _paint(frame, clear)


def display_lyrics(
    text: str,
    font_data: dict = None,
    notes=None,
    color: Optional[RGB] = None,
    clear: bool = False,
):
    """
    Display a lyric line with the ambient music notes drifting behind it.

    Args:
        text: Lyric line to display
        font_data: Font to use for block letters (plain centered text if None)
        notes: Iterable of (row, col, glyph) background notes, or None
        color: Optional RGB to paint the lyric letters in (e.g. the album
            cover's accent colour); notes stay dim grey regardless
        clear: Force a full clear before painting
    """
    if font_data:
        frame = render_block_text(text, font_data)
    else:
        frame = render_simple_text(text)
    if notes or color is not None:
        frame = _compose_lyric(frame, notes, color)
    _paint(frame, clear)
