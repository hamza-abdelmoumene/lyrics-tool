#!/usr/bin/env python3
"""Regenerate the README preview images from the *real* renderer.

Rather than screen-recording a live session, this drives the actual rendering
functions in :mod:`lyrics_tool.visualizer_display` with synthetic player state,
captures the ANSI frames they emit, and rasterises them to PNG/GIF with Pillow
and a monospace font. The block letters, colours, notes, glitch and ad screens
are therefore exactly what the terminal shows — just reproducibly, in CI or on
any machine, with no player or audio needed.

    python tools/generate_previews.py            # writes into assets/

Lyrics shown are original placeholder lines (no copyrighted content).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lyrics_tool import visualizer_display as vd  # noqa: E402
from lyrics_tool.effects import NoteField  # noqa: E402
from lyrics_tool.fonts import get_font  # noqa: E402

# ── canvas / theme ───────────────────────────────────────────────────────────
COLS, ROWS = 84, 24
FONT_SIZE = 26
PAD = 28
BAR_H = 44
WIN_BG = (17, 18, 23)          # terminal background
BAR_BG = (28, 30, 37)
DOTS = [(255, 95, 86), (255, 189, 46), (39, 201, 63)]
DEFAULT_FG = (222, 224, 230)

FONT_CANDIDATES = [
    "/usr/share/fonts/TTF/JetBrainsMonoNerdFontMono-Regular.ttf",
    "/usr/share/fonts/TTF/JetBrainsMono-Regular.ttf",
    str(Path.home() / ".local/share/fonts/JetBrainsMono/JetBrainsMono-Regular.ttf"),
    "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf",
    "/Library/Fonts/JetBrainsMono-Regular.ttf",
    "DejaVuSansMono.ttf",  # Pillow ships this; has block glyphs
]


def _load_font() -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, FONT_SIZE)
        except Exception:
            continue
    raise SystemExit("No usable monospace font found; install JetBrains Mono.")


FONT = _load_font()
_asc, _desc = FONT.getmetrics()
CELL_W = round(FONT.getlength("█")) or FONT_SIZE // 2
CELL_H = _asc + _desc

# JetBrains Mono lacks most musical-note glyphs, so route those (and anything
# else the primary font can't draw) to a symbol font that covers them.
_NOTE_FONT_CANDIDATES = [
    "/usr/share/fonts/noto/NotoSansSymbols-Regular.ttf",
    "/usr/share/fonts/**/NotoSansSymbols-Regular.ttf",
    "/usr/share/fonts/**/DejaVuSans.ttf",
]


def _load_note_font():
    import glob
    for pat in _NOTE_FONT_CANDIDATES:
        for path in sorted(glob.glob(pat, recursive=True)) or [pat]:
            try:
                return ImageFont.truetype(path, FONT_SIZE - 3)
            except Exception:
                continue
    return FONT


NOTE_FONT = _load_note_font()
_TOFU = bytes(FONT.getmask("￾"))


def _has_glyph(font, ch: str) -> bool:
    m = bytes(font.getmask(ch))
    return m != _TOFU and m.strip(b"\x00") != b""


_font_cache: dict = {}


def _font_for(ch: str):
    """Pick the first font that can render ``ch`` (primary, then symbol font)."""
    if ch not in _font_cache:
        if _has_glyph(FONT, ch):
            _font_cache[ch] = (FONT, ch, False)
        elif _has_glyph(NOTE_FONT, ch):
            _font_cache[ch] = (NOTE_FONT, ch, True)
        else:
            _font_cache[ch] = (FONT, "·", False)  # last-resort subtle dot
    return _font_cache[ch]

_SGR = re.compile(r"\x1b\[([0-9;]*)m")


def _xterm256(n: int) -> tuple:
    if n < 16:
        base = [(0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0), (0, 0, 128),
                (128, 0, 128), (0, 128, 128), (192, 192, 192), (128, 128, 128),
                (255, 0, 0), (0, 255, 0), (255, 255, 0), (0, 0, 255),
                (255, 0, 255), (0, 255, 255), (255, 255, 255)]
        return base[n]
    if n < 232:
        n -= 16
        r, g, b = n // 36, (n % 36) // 6, n % 6
        conv = lambda c: 0 if c == 0 else 55 + c * 40  # noqa: E731
        return (conv(r), conv(g), conv(b))
    grey = 8 + (n - 232) * 10
    return (grey, grey, grey)


def _cells(line: str):
    """Yield (col, char, fg, bg) for one ANSI line, tracking SGR state."""
    fg, bg = DEFAULT_FG, None
    col = i = 0
    while i < len(line):
        m = _SGR.match(line, i)
        if m:
            params = [p for p in m.group(1).split(";") if p != ""] or ["0"]
            j = 0
            while j < len(params):
                p = params[j]
                if p == "0":
                    fg, bg = DEFAULT_FG, None
                elif p == "38" and params[j + 1:j + 2] == ["2"]:
                    fg = tuple(int(x) for x in params[j + 2:j + 5])
                    j += 4
                elif p == "38" and params[j + 1:j + 2] == ["5"]:
                    fg = _xterm256(int(params[j + 2]))
                    j += 2
                elif p == "48" and params[j + 1:j + 2] == ["2"]:
                    bg = tuple(int(x) for x in params[j + 2:j + 5])
                    j += 4
                elif p == "2":  # dim
                    fg = tuple(int(c * 0.55) for c in fg)
                j += 1
            i = m.end()
            continue
        yield col, line[i], fg, bg
        col += 1
        i += 1


def frame_to_image(frame: str, label: str = "lyricsooo") -> Image.Image:
    w = COLS * CELL_W + 2 * PAD
    h = BAR_H + ROWS * CELL_H + 2 * PAD
    img = Image.new("RGB", (w, h), WIN_BG)
    d = ImageDraw.Draw(img)

    # window chrome: title bar + traffic-light dots + centred command label
    d.rectangle([0, 0, w, BAR_H], fill=BAR_BG)
    for k, colour in enumerate(DOTS):
        cx = 22 + k * 22
        d.ellipse([cx - 6, BAR_H // 2 - 6, cx + 6, BAR_H // 2 + 6], fill=colour)
    d.text((w // 2, BAR_H // 2), label, font=FONT, fill=(150, 154, 165), anchor="mm")

    top = BAR_H + PAD
    for ri, row in enumerate(frame.split("\n")[:ROWS]):
        y = top + ri * CELL_H
        for col, ch, fg, bg in _cells(row):
            if col >= COLS:
                break
            x = PAD + col * CELL_W
            if bg is not None:
                d.rectangle([x, y, x + CELL_W, y + CELL_H], fill=bg)
            if ch == "█":
                # Fill the whole cell so stacked block letters are seamless
                # (the font glyph leaves hairline seams between cells).
                d.rectangle([x, y, x + CELL_W, y + CELL_H], fill=fg)
            elif ch != " ":
                cell_font, glyph, centered = _font_for(ch)
                if centered:  # symbol glyphs: centre in the cell
                    d.text((x + CELL_W / 2, y + CELL_H / 2), glyph,
                           font=cell_font, fill=fg, anchor="mm")
                else:
                    d.text((x, y), glyph, font=cell_font, fill=fg)
    return img


def save_png(frame: str, name: str, label: str = "lyricsooo") -> None:
    frame_to_image(frame, label).save(ASSETS / name)
    print(f"  wrote {name}")


def save_gif(frames, name: str, label: str = "lyricsooo", duration=120) -> None:
    imgs = [frame_to_image(f, label) for f in frames]
    imgs[0].save(ASSETS / name, save_all=True, append_images=imgs[1:],
                 duration=duration, loop=0, optimize=True, disposal=2)
    print(f"  wrote {name}  ({len(imgs)} frames)")


# ── frame builders (drive the real renderer) ─────────────────────────────────
ASSETS = ROOT / "assets"
BLOCK = get_font("block")
vd.get_terminal_size = lambda: (COLS, ROWS)   # fix the "terminal" size


def _notes(t: float, seed: int = 7):
    return NoteField(seed=seed).positions(COLS, ROWS, t)


def lyric_frame(text: str, t: float, color, seed: int = 7) -> str:
    vd._render_cache.clear()
    base = vd.render_block_text(text.upper(), BLOCK)
    return vd._compose_lyric(base, _notes(t, seed), color)


def build_visualizer_gif():
    accent = (120, 205, 235)   # cool cyan lyric accent
    line = "INTO THE NIGHT"
    frames = [lyric_frame(line, t * 0.5, accent) for t in range(14)]
    save_gif(frames, "image-preview.gif", duration=140)


def build_phrase_gif():
    accent = (238, 170, 96)    # warm amber
    lines = ["HOLD ON TO THE LIGHT", "AND WE'LL BE FINE",
             "CHASING EVERY SPARK", "UNTIL THE MORNING"]
    frames = []
    t = 0.0
    for ln in lines:
        for k in range(4):     # a few frames per line so notes drift
            frames.append(lyric_frame(ln, t, accent))
            t += 0.5
    save_gif(frames, "song-phrase-preview.gif", duration=260)


def build_switching_gif():
    bg, fg = (122, 54, 140), (240, 236, 246)   # cover-tinted card
    artist, title = "AURORA SKIES", "MIDNIGHT"
    base = vd.render_now_playing(artist, title, BLOCK)
    frames = []
    N = 9
    for k in range(N):                          # glitch burst decaying to clean
        amount = 1.0 - (k / max(1, N))
        g = vd._glitch_frame(base, COLS, amount)
        g = vd._glitch_tint(g, bg, fg, amount)
        frames.append(g)
    settled = vd._tint_frame(base, bg, fg)
    frames += [settled] * 5                      # hold the settled card
    save_gif(frames, "switching-preview.gif", duration=90)


def build_colors_png():
    # The dominant-cover tint painting the whole now-playing card.
    bg, fg = (188, 74, 60), (250, 244, 240)      # warm terracotta cover
    base = vd.render_now_playing("SOLAR FIELDS", "GOLDEN HOUR", BLOCK)
    save_png(vd._tint_frame(base, bg, fg), "colors-preview.png")


def build_ads_gif():
    accent = (150, 160, 175)
    frames = [vd._compose_lyric(vd.render_ad_screen(BLOCK, phase=p), _notes(p * 0.4), accent)
              for p in range(16)]
    save_gif(frames, "ads-preview.gif", duration=200)


def main():
    ASSETS.mkdir(exist_ok=True)
    print(f"Font: {FONT.path}  cell={CELL_W}x{CELL_H}  canvas={COLS}x{ROWS}")
    build_visualizer_gif()
    build_phrase_gif()
    build_switching_gif()
    build_colors_png()
    build_ads_gif()
    print("Done.")


if __name__ == "__main__":
    main()
