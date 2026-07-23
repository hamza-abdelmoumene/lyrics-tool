"""
lyricsooo — live terminal lyrics visualizer (playerctl/MPRIS).
"""
import argparse
import sys
from pathlib import Path

from .paths import processed_dir, ensure_dir


def main():
    from .keyinput import enable_ansi
    enable_ansi()  # switch the Windows console into VT mode (no-op elsewhere)

    parser = argparse.ArgumentParser(
        prog='lyricsooo',
        description='Live terminal lyrics visualizer synced to your player '
                    '(MPRIS/playerctl · Windows SMTC · macOS nowplaying-cli)',
    )
    parser.add_argument('--lrc-dir', type=Path, default=None,
                        help='Directory of LRC files to display '
                             '(default: ~/.local/share/lyrics-tool/lyrics/processed)')
    parser.add_argument('--audio-dir', type=Path,
                        help='Directory containing audio files')
    parser.add_argument('--wlrc', action='store_true',
                        help='LRC files are word-level (WLRC format)')
    parser.add_argument('--font', type=str, default='block',
                        help='Font to use (default: block)')
    parser.add_argument('--custom-fonts', type=Path,
                        help='Path to custom fonts JSON file')
    parser.add_argument('--refresh-rate', type=float, default=0.05,
                        help='Display refresh rate in seconds (default: 0.05)')
    parser.add_argument('--offset', type=float, default=0.0,
                        help='Lyric sync offset in seconds: positive shows '
                             'lyrics earlier, negative later. Default 0 matches '
                             'the desktop media widget exactly. Stacks with any '
                             'live nudge saved via the +/- keys and with '
                             '$LYRICSOOO_LYRIC_LEAD (default: 0)')
    parser.add_argument('--no-cover-color', action='store_true',
                        help='Disable all colour tinting (card + lyrics); use '
                             'the terminal default foreground')
    parser.add_argument('--color-source', type=str, default=None,
                        metavar='SOURCE',
                        help="Where lyric/card colours come from: 'art' "
                             "(album-art tint, default), 'none', a desktop "
                             "preset ('pywal', 'caelestia', 'matugen'), "
                             "'fixed:#rrggbb', or 'file:PATH' for any JSON "
                             "theme. Also settable via $LYRICSOOO_COLOR_SOURCE")
    parser.add_argument('--theme-file', type=Path, default=None,
                        help='Override the JSON theme file path for the '
                             'chosen preset / file colour source')
    parser.add_argument('--no-notes', action='store_true',
                        help='Disable the floating music notes behind lyrics')
    parser.add_argument('--player', type=str, default=None,
                        help='MPRIS player to follow (e.g. spotify, mpv, vlc). '
                             'Default: auto-detect the active player, so both '
                             'Spotify and local players work out of the box')
    parser.add_argument('--ignore-player', type=str, default=None, metavar='LIST',
                        help="Comma-separated MPRIS players auto-detect must never "
                             "follow. Defaults to web browsers and chat/telephony "
                             "apps, so a YouTube lecture or a Telegram voice message "
                             "can't hijack the lyrics from your music. Auto-detect "
                             "otherwise prefers whatever is actually playing. Pass '' "
                             "to follow anything. Ignored when --player pins a player.")
    parser.add_argument('--player-backend', type=str, default=None, metavar='NAME',
                        help="Force the now-playing source: 'playerctl' "
                             "(Linux/MPRIS), 'smtc' (Windows), 'nowplaying-cli' "
                             "(macOS). Default: auto-detect for your OS. Also "
                             "settable via $LYRICSOOO_PLAYER_BACKEND.")
    parser.add_argument('--banner-hold', type=float, default=1.5,
                        help='Seconds the settled song-title card stays up on a '
                             'track switch before lyrics take over, timed after '
                             'the glitch resolves (default: 1.5)')
    parser.add_argument('--reveal', type=str, default=None,
                        choices=['standard', 'typewriter', 'fade', 'glow'],
                        help='Line reveal effect (all optional, one at a time): '
                             "'standard' (instant), 'typewriter' (char-by-char), "
                             "'fade' (soft fade-in per line), 'glow' (the active "
                             "line gently breathes). Default: standard.")
    parser.add_argument('--typewriter', action='store_true',
                        help='Shorthand for --reveal typewriter (phrase-level '
                             'mode only; ignored with --wlrc).')
    parser.add_argument('--select', action='store_true',
                        help='Interactive picker before starting: choose the reveal '
                             'effect (standard/typewriter/fade/glow) and style '
                             '(phrase/word).')
    parser.add_argument('--config', type=Path,
                        help='Path to config.yaml')

    args = parser.parse_args()

    # Reveal effect + style may be set by flags now and overridden by the --select
    # picker once the colour source is known (so the card is themed). Resolved
    # below. --reveal wins; --typewriter is a legacy shorthand for it.
    reveal = args.reveal or ('typewriter' if args.typewriter else 'standard')
    wlrc = args.wlrc

    # Resolve the lyrics directory. With no --lrc-dir we use the shared default
    # location and create it if missing, so a fresh install runs immediately:
    # the visualizer fetches and caches lyrics on the fly as tracks play.
    if args.lrc_dir is None:
        lrc_dir = ensure_dir(processed_dir())
        if not any(lrc_dir.iterdir()):
            print(f"No cached lyrics yet in {lrc_dir}.")
            print("They'll be fetched automatically as tracks play.")
            print("Tip: bulk-download in advance with  lyricsooo-fetch --audio-dir ~/Music")
            print()
    else:
        lrc_dir = args.lrc_dir
        if not lrc_dir.exists():
            print(f"Error: LRC directory {lrc_dir} does not exist", file=sys.stderr)
            return 1

    try:
        from .fonts import get_font, load_fonts_from_json, register_font
        from .visualizer_main import run_visualizer
        from .visualizer_player import set_player, set_ignored, set_backend, backend_name
        from .theme_source import make_color_provider
    except ImportError as e:
        print(f"Error: could not import visualizer modules — {e}")
        return 1

    # Pick the now-playing backend for this OS (or honour an explicit override),
    # then warn if this platform has no live-sync source available.
    if args.player_backend:
        set_backend(args.player_backend)
    if backend_name() == 'none':
        print("Note: no live-sync backend is available on this system, so the",
              file=sys.stderr)
        print("visualizer can't follow a player. Install one:", file=sys.stderr)
        print("  · Linux  — playerctl        · Windows — pip install "
              "'lyrics-tool[windows]'", file=sys.stderr)
        print("  · macOS  — brew install nowplaying-cli", file=sys.stderr)
        print("The offline tools lyricsooo-fetch / lyricsooo-cook still work.\n",
              file=sys.stderr)

    # Follow a specific player, or auto-detect the active one (Spotify/local).
    set_player(args.player)
    # Skip browsers on auto-detect (default) unless the user customises the list.
    if args.ignore_player is not None:
        set_ignored(args.ignore_player)

    # Resolve the colour source. Precedence: CLI flag > env var > default 'art'.
    # The env var lets a rice / shell rc pin a system-wide default (e.g.
    #   export LYRICSOOO_COLOR_SOURCE=pywal) without touching every launch.
    import os
    cover_color = not args.no_cover_color
    source = args.color_source or os.environ.get('LYRICSOOO_COLOR_SOURCE') or 'art'
    theme_file = str(args.theme_file) if args.theme_file else None
    color_provider = make_color_provider(source, theme_file=theme_file) if cover_color else None

    # Load custom fonts if provided
    if args.custom_fonts:
        if not args.custom_fonts.exists():
            print(f"Error: custom fonts file {args.custom_fonts} does not exist", file=sys.stderr)
            return 1
        custom = load_fonts_from_json(args.custom_fonts)
        for name, data in custom.items():
            if not name.startswith('_'):  # skip comment keys
                register_font(name, data)

    font_data = get_font(args.font)

    # Optional interactive picker (themed with the resolved colour source).
    if args.select:
        from .selector import choose
        _c = color_provider.current() if color_provider is not None else None
        accent = _c.lyric if (_c and _c.lyric) else (219, 199, 102)
        picks = choose(accent, reveal=reveal, wlrc=wlrc)
        reveal, wlrc = picks['reveal'], picks['wlrc']
    if reveal == 'typewriter' and wlrc:
        reveal = 'standard'  # typewriter is a phrase-mode reveal; word mode wins

    print("Starting LRC visualizer...")
    print(f"LRC directory: {lrc_dir}")
    print(f"Font: {args.font}")
    print(f"Player backend: {backend_name()}")
    if cover_color:
        print(f"Colour source: {source}")
    print("Sync: press  -  /  +  to slide lyrics later / earlier · 0 to reset (saved)")
    print("Press Ctrl+C to exit")
    print()

    try:
        run_visualizer(
            lrc_dir=lrc_dir,
            audio_dir=args.audio_dir,
            is_wlrc=wlrc,
            font_data=font_data,
            refresh_rate=args.refresh_rate,
            sync_offset=args.offset,
            cover_color=cover_color,
            notes=not args.no_notes,
            banner_hold=args.banner_hold,
            reveal=reveal,
            color_provider=color_provider,
        )
    except KeyboardInterrupt:
        print("\nExiting...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
