"""
Pluggable colour sources for the visualiser — portable across any system.

The visualiser paints two things with colour: the *lyric* text tint and the
now-playing *card* (background + foreground). Where those colours come from is
deliberately abstracted here so the tool works the same on every setup:

* ``art``       — dominant colour of the current track's album art (the default;
                  needs nothing but Pillow, works on any distro/player).
* ``none``      — no colour; lyrics use the terminal's default foreground.
* ``pywal``     — follow the active ``wal``/``pywal`` palette (``colors.json``).
* ``caelestia`` — follow the Caelestia desktop scheme (Material-You ``scheme.json``).
* ``file:PATH`` — follow *any* JSON theme file, with a configurable key map, so
                  matugen / wallust / a hand-written palette all work.

Two resolution flavours are unified behind one :class:`ColorProvider` interface:

* **per-track** (album art) — colours are a property of the song, so they are
  (re)resolved off-thread on every track change and read once ready.
* **continuous** (theme files) — colours are a property of the *desktop* and can
  change at any moment, so they are re-read cheaply (mtime-gated) every frame.

The visualiser doesn't need to know which flavour it holds: it calls
:meth:`ColorProvider.on_track` on each song and :meth:`ColorProvider.current`
whenever it wants the latest colours.
"""
from __future__ import annotations

import json
import os
import threading
from collections import namedtuple
from typing import Dict, Optional, Tuple

RGB = Tuple[int, int, int]

# (lyric, card_bg, card_fg) — any field may be None to mean "leave as default".
Colors = namedtuple("Colors", "lyric card_bg card_fg")


def _hex_to_rgb(hx: str) -> Optional[RGB]:
    """Parse ``#rrggbb`` / ``rrggbb`` (and short ``#rgb``) into an RGB triple."""
    if not isinstance(hx, str):
        return None
    hx = hx.strip().lstrip("#")
    if len(hx) == 3:  # short form: #abc -> #aabbcc
        hx = "".join(c * 2 for c in hx)
    if len(hx) < 6:
        return None
    try:
        return (int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16))
    except ValueError:
        return None


def _dig(data: dict, dotted: Optional[str]):
    """Walk ``data`` by a dotted path (``"colours.primary"``); None if absent."""
    if not dotted:
        return None
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #
class ColorProvider:
    """Base class: supplies ``Colors`` for the currently playing track.

    Subclasses override :meth:`on_track` (called once per song) and/or
    :meth:`current` (polled by the render loop). ``continuous`` tells the loop
    whether colours may drift mid-song (theme files) or are fixed per track
    (album art); it uses this only to decide how eagerly to re-check.
    """

    continuous: bool = False

    def on_track(self, art_url: Optional[str]) -> None:  # noqa: D401 - hook
        """Notify the provider a new track started (``art_url`` may be None)."""

    def current(self) -> Optional[Colors]:
        """Return the latest known colours, or None if not resolved yet."""
        return None


class NullColorProvider(ColorProvider):
    """No colour at all — lyrics stay in the terminal's default foreground."""

    def current(self) -> Optional[Colors]:
        return None


class FixedColorProvider(ColorProvider):
    """A single, static accent colour (``fixed:#rrggbb``)."""

    def __init__(self, lyric: RGB):
        self._colors = Colors(lyric, None, None)

    def current(self) -> Optional[Colors]:
        return self._colors


class ArtColorProvider(ColorProvider):
    """Dominant album-art colour, resolved off-thread per track (portable default).

    The image download must never block the announce, so each track kicks a
    daemon thread; :meth:`current` returns None until it lands, then the vivid
    card colours and a soft lyric accent.
    """

    continuous = False

    def __init__(self) -> None:
        self._holder: Optional[dict] = None

    def on_track(self, art_url: Optional[str]) -> None:
        holder: dict = {"done": False, "colors": None}
        self._holder = holder

        def work() -> None:
            try:
                from .cover import cover_colors, lyric_accent, text_color, vivid

                colors = cover_colors(art_url)
                if colors:
                    raw_bg = colors[0]
                    card_bg = vivid(raw_bg)
                    holder["colors"] = Colors(
                        lyric_accent(raw_bg), card_bg, text_color(card_bg)
                    )
            except Exception:
                pass
            finally:
                holder["done"] = True

        threading.Thread(target=work, daemon=True).start()

    def current(self) -> Optional[Colors]:
        holder = self._holder
        if holder and holder["done"]:
            return holder["colors"]
        return None


class ThemeFileColorProvider(ColorProvider):
    """Follow a JSON theme file, mapping named keys to lyric/card colours.

    Cheap to poll: the file is only re-parsed when its mtime changes, so calling
    :meth:`current` every frame costs a single ``stat`` in the steady state.
    Keys are dotted paths from the JSON root (``"colours.primary"``), which
    covers both flat and nested palettes (Caelestia, pywal, matugen, …).
    """

    continuous = True

    def __init__(
        self,
        path: str,
        lyric_key: Optional[str],
        card_bg_key: Optional[str] = None,
        card_fg_key: Optional[str] = None,
    ) -> None:
        self._path = os.path.expanduser(path)
        self._lyric_key = lyric_key
        self._card_bg_key = card_bg_key
        self._card_fg_key = card_fg_key
        self._mtime = 0.0
        self._cached: Optional[Colors] = None

    def current(self) -> Optional[Colors]:
        try:
            mtime = os.stat(self._path).st_mtime
            if mtime != self._mtime or self._cached is None:
                with open(self._path) as f:
                    data = json.load(f)
                self._cached = Colors(
                    _hex_to_rgb(_dig(data, self._lyric_key)) if self._lyric_key else None,
                    _hex_to_rgb(_dig(data, self._card_bg_key)) if self._card_bg_key else None,
                    _hex_to_rgb(_dig(data, self._card_fg_key)) if self._card_fg_key else None,
                )
                self._mtime = mtime
        except Exception:
            # File missing/unreadable/malformed: keep whatever we last had.
            pass
        return self._cached


# --------------------------------------------------------------------------- #
# Presets & factory
# --------------------------------------------------------------------------- #
# name -> (path, lyric_key, card_bg_key, card_fg_key)
PRESETS: Dict[str, Tuple[str, str, str, str]] = {
    # Caelestia writes a Material-You scheme under XDG state.
    "caelestia": (
        "~/.local/state/caelestia/scheme.json",
        "colours.primary",
        "colours.surfaceContainerHigh",
        "colours.onSurface",
    ),
    # pywal / wal palette: 16 ANSI colours + special bg/fg.
    "pywal": (
        "~/.cache/wal/colors.json",
        "colors.color4",
        "colors.color0",
        "special.foreground",
    ),
    # matugen's JSON export uses snake_case Material-You role names.
    "matugen": (
        "~/.cache/matugen/colors.json",
        "colors.primary",
        "colors.surface_container_high",
        "colors.on_surface",
    ),
}

# Friendly aliases.
_ALIASES = {"wal": "pywal", "album": "art", "cover": "art", "off": "none"}


def make_color_provider(
    source: Optional[str],
    *,
    theme_file: Optional[str] = None,
    lyric_key: Optional[str] = None,
    card_bg_key: Optional[str] = None,
    card_fg_key: Optional[str] = None,
) -> ColorProvider:
    """Build a :class:`ColorProvider` from a source spec.

    ``source`` is one of ``art``, ``none``, a preset name (``caelestia``,
    ``pywal``, ``matugen``), ``fixed:#rrggbb``, ``file:PATH``, or a bare path to
    a JSON theme file. ``theme_file`` / ``*_key`` override the preset or supply
    the mapping for a generic ``file`` source. Unknown specs fall back to
    ``art`` so the tool never crashes on a typo.
    """
    spec = (source or "art").strip()
    spec = _ALIASES.get(spec.lower(), spec)
    low = spec.lower()

    if low in ("none", ""):
        return NullColorProvider()
    if low == "art":
        return ArtColorProvider()
    if low.startswith("fixed:"):
        rgb = _hex_to_rgb(spec.split(":", 1)[1])
        return FixedColorProvider(rgb) if rgb else ArtColorProvider()

    # Explicit generic file source: file:/path/to/theme.json
    if low.startswith("file:"):
        path = spec.split(":", 1)[1]
        return ThemeFileColorProvider(
            theme_file or path,
            lyric_key or "colors.color4",
            card_bg_key,
            card_fg_key,
        )

    # Named preset (optionally with per-key overrides).
    if low in PRESETS:
        p_path, p_lyric, p_bg, p_fg = PRESETS[low]
        return ThemeFileColorProvider(
            theme_file or p_path,
            lyric_key or p_lyric,
            card_bg_key or p_bg,
            card_fg_key or p_fg,
        )

    # A bare filesystem path pointing at a JSON theme.
    if os.path.exists(os.path.expanduser(spec)) or theme_file:
        return ThemeFileColorProvider(
            theme_file or spec,
            lyric_key or "colors.color4",
            card_bg_key,
            card_fg_key,
        )

    # Unknown → safest portable default.
    return ArtColorProvider()
