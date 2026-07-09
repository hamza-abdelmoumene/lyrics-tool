"""
lyricsooo — live terminal lyrics visualizer (playerctl/MPRIS).
"""
import argparse
import sys
from pathlib import Path

from .paths import processed_dir, ensure_dir


def main():
    parser = argparse.ArgumentParser(
        prog='lyricsooo',
        description='Live terminal lyrics visualizer with playerctl/MPRIS sync',
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
                        help='Extra lyric sync offset in seconds on top of the '
                             'built-in lead: positive shows lyrics earlier, '
                             'negative later (default: 0)')
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
                             "follow. Defaults to web browsers, so a YouTube "
                             "lecture/course playing in Firefox/Chrome can't hijack "
                             "the lyrics from your music. Pass '' to follow anything. "
                             "Ignored when --player pins a specific player.")
    parser.add_argument('--banner-hold', type=float, default=1.5,
                        help='Seconds the settled song-title card stays up on a '
                             'track switch before lyrics take over, timed after '
                             'the glitch resolves (default: 1.5)')
    parser.add_argument('--typewriter', action='store_true',
                        help='Typewriter effect: progressively reveal each '
                             'lyric line character by character (phrase-level '
                             'mode only; ignored with --wlrc)')
    parser.add_argument('--config', type=Path,
                        help='Path to config.yaml')

    args = parser.parse_args()

    typewriter = args.typewriter
    if typewriter and args.wlrc:
        print('Warning: --typewriter is ignored in word-level mode (--wlrc)',
              file=sys.stderr)
        typewriter = False

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
        from .visualizer_player import set_player, set_ignored
        from .theme_source import make_color_provider
    except ImportError as e:
        print(f"Error: could not import visualizer modules — {e}")
        return 1

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

    print("Starting LRC visualizer...")
    print(f"LRC directory: {lrc_dir}")
    print(f"Font: {args.font}")
    if cover_color:
        print(f"Colour source: {source}")
    print("Press Ctrl+C to exit")
    print()

    try:
        run_visualizer(
            lrc_dir=lrc_dir,
            audio_dir=args.audio_dir,
            is_wlrc=args.wlrc,
            font_data=font_data,
            refresh_rate=args.refresh_rate,
            sync_offset=args.offset,
            cover_color=cover_color,
            notes=not args.no_notes,
            banner_hold=args.banner_hold,
            typewriter=typewriter,
            color_provider=color_provider,
        )
    except KeyboardInterrupt:
        print("\nExiting...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
