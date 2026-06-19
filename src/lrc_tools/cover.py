"""
Album-art colour extraction for the now-playing card.

Pulls the dominant colour out of the current track's cover so the song-name
card can paint the terminal in that colour (with readable white/dark text).
All lookups are cached by art URL, so re-announcing the same track — or
flipping back to a previous one — never re-downloads or re-decodes the image.
"""
import colorsys
from io import BytesIO
from typing import Optional, Tuple
from urllib import request

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:  # Pillow is optional; cards just stay uncoloured without it.
    PIL_AVAILABLE = False

RGB = Tuple[int, int, int]

# url -> (bg, fg) | None  (None caches a miss so we don't retry the network)
_color_cache: dict = {}


def _luminance(rgb: RGB) -> float:
    """Perceptual luminance in 0..255 (Rec. 601 weighting)."""
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def text_color(bg: RGB) -> RGB:
    """Pick a readable foreground for ``bg``: near-black on light, near-white on dark."""
    return (18, 18, 18) if _luminance(bg) > 150 else (240, 240, 240)


def lyric_accent(rgb: RGB) -> RGB:
    """A soft, legible lyric-text colour derived from a cover colour.

    The raw dominant can be near-black (dark navy covers) or eye-searingly
    saturated. Keeping its *hue* but forcing a high value and pulling the
    saturation down to a gentle band yields a calm, readable tint on the default
    background — saturated punch is reserved for the title card, not the lyrics.
    """
    r, g, b = (c / 255 for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.12:  # near-greyscale cover: hue is meaningless, don't invent one
        return (210, 210, 210)
    s = min(max(s * 0.6, 0.28), 0.5)  # softer than the card; never garish
    v = max(v, 0.85)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (round(r * 255), round(g * 255), round(b * 255))


def vivid(rgb: RGB) -> RGB:
    """Punch up a cover colour's saturation for the title-card background.

    The card is meant to read boldly as "the album's colour", so we deepen the
    saturation (without lightening it — :func:`text_color` adapts the text to the
    result, dark on light cards and light on dark ones).
    """
    r, g, b = (c / 255 for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    s = min(1.0, s * 1.25 + 0.08)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (round(r * 255), round(g * 255), round(b * 255))


def _download(url: str, timeout: float = 4.0) -> Optional[bytes]:
    """Fetch raw image bytes from an http(s) URL or a local ``file://`` path."""
    try:
        if url.startswith('file://'):
            with open(url[7:], 'rb') as f:
                return f.read()
        with request.urlopen(url, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def dominant_color(data: bytes) -> Optional[RGB]:
    """Extract a representative, pleasing accent colour from image bytes.

    Quantises to a small palette and scores each swatch by how common it is,
    nudged toward saturated mid-tones — this avoids a muddy average and skips
    the flat black/white borders many covers have, so the card gets the colour
    a person would actually call "the album's colour".
    """
    if not PIL_AVAILABLE:
        return None
    try:
        img = Image.open(BytesIO(data)).convert('RGB')
        img.thumbnail((64, 64))
        quant = img.quantize(colors=8, method=Image.Quantize.FASTOCTREE)
        palette = quant.getpalette()
        counts = quant.getcolors() or []
    except Exception:
        return None

    best: Optional[RGB] = None
    best_score = -1.0
    for count, idx in counts:
        r, g, b = palette[idx * 3:idx * 3 + 3]
        mx, mn = max(r, g, b), min(r, g, b)
        sat = (mx - mn) / mx if mx else 0.0
        lum = _luminance((r, g, b)) / 255.0
        # Common + saturated wins; pure black/white (lum at the extremes) loses.
        score = count * (0.35 + sat) * (1.0 - abs(lum - 0.5) * 0.6)
        if score > best_score:
            best_score = score
            best = (r, g, b)
    return best


def cover_colors(url: Optional[str]) -> Optional[Tuple[RGB, RGB]]:
    """Return ``(bg, fg)`` for an art URL, or None when unavailable.

    Cached per URL (including misses) so it's safe to call on every track
    announcement without hitting the network twice for the same cover.
    """
    if not url or not PIL_AVAILABLE:
        return None
    if url in _color_cache:
        return _color_cache[url]

    data = _download(url)
    bg = dominant_color(data) if data else None
    result = (bg, text_color(bg)) if bg else None
    _color_cache[url] = result
    return result
