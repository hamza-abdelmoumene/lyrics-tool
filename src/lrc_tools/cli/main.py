import argparse
import sys
from lrc_tools.__about__ import __version__
from lrc_tools.cli import fetch, process, vis

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="lyrics-tool",
        description="Terminal lyrics visualizer and LRC/WLRC processing suite.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    fetch.setup_parser(subparsers)
    process.setup_parser(subparsers)
    vis.setup_parser(subparsers)
    
    args = parser.parse_args()
    
    import logging
    level = logging.DEBUG if args.debug else (logging.INFO if args.verbose else logging.WARNING)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s" if args.debug else "%(message)s",
        datefmt="%H:%M:%S",
    )
    
    sys.exit(args.func(args))

if __name__ == '__main__':
    main()
