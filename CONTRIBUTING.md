# Contributing to lyrics-tool

Thanks for your interest in contributing! This guide covers setup on every OS,
the project layout, and how to get a change merged.

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Prerequisites

- **Python ≥ 3.9**
- A live player to test the visualizer against (optional — the whole test suite
  runs without one):
  - **Linux** — [`playerctl`](https://github.com/altdesktop/playerctl)
  - **Windows** — the `[windows]` extra (`pip install -e '.[windows]'`) for the
    System Media Transport Controls backend
  - **macOS** — [`nowplaying-cli`](https://github.com/kirtan-shah/nowplaying-cli)
    (`brew install nowplaying-cli`)
- **ffmpeg** (`ffprobe`) — optional, for audio-duration detection in the processor

## Development setup

```bash
git clone https://github.com/hamza-abdelmoumene/lyrics-tool.git
cd lyrics-tool

python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows (PowerShell):
#   .venv\Scripts\Activate.ps1

pip install -e '.[dev]'
```

This registers the `lyricsooo`, `lyricsooo-fetch`, and `lyricsooo-cook`
commands in your virtualenv.

## Running the checks

```bash
pytest                       # full suite — no playerctl, audio, or network needed
ruff check .                 # lint
mypy src                     # types (informational)
```

The suite drives the visualizer loop with a **stubbed player** and asserts track
announces, graceful no-lyrics handling, and that a slow fetch never blocks the
display. Every OS-specific backend is unit-tested through fakes, so the suite is
fully cross-platform — please keep it that way (no test should require a real
`playerctl` / `winsdk` / `nowplaying-cli`).

## Project layout

```
src/lyrics_tool/
├── cli_visualizer.py      # `lyricsooo` entry point (argument parsing)
├── cli_fetch.py           # `lyricsooo-fetch`
├── cli_cook.py            # `lyricsooo-cook`
├── visualizer_main.py     # the display loop + background position monitor
├── visualizer_display.py  # block-letter rendering, tinting, diff paint
├── visualizer_player.py   # thin facade over the selected player backend
├── players/               # cross-platform now-playing backends
│   ├── base.py            #   NowPlaying snapshot + PlayerBackend protocol
│   ├── playerctl.py       #   Linux/BSD (MPRIS)
│   ├── windows.py         #   Windows (SMTC / winsdk)
│   └── macos.py           #   macOS (nowplaying-cli)
├── keyinput.py            # cross-platform key reading (POSIX + Windows)
├── sync.py                # phase-locked playback clock
├── effects.py             # ambient notes + line-reveal colour maths
├── theme_source.py        # pluggable colour providers
├── parser.py / processor_*.py / puller.py   # LRC/WLRC IO + fetch + prepare
└── ...
```

### Adding a player backend

Live sync on a new platform is a self-contained change:

1. Add a module under `players/` with a `PlayerBackend` subclass. Implement
   `available()` (a cheap, OS-guarded probe) and `snapshot()` returning a
   `NowPlaying`; optionally `art_url()` / `audio_file()`. **Guard every
   platform-specific import inside the methods** so importing the module is safe
   on any OS.
2. Register it in `players/__init__._BACKENDS` and add friendly `_ALIASES`.
3. Add tests that exercise your parsing/selection logic through fakes (see
   `tests/test_players.py`) — no real device required.

## Code style

- Follow the existing patterns: `RGB` tuples, `_paint()` diff rendering,
  lock-free `SyncData`, terse one-line docstrings that explain *why*.
- Use type hints where practical. Keep functions focused.
- `ruff check .` must pass; `mypy` is informational but don't add new errors.

## Commits & pull requests

- Use clear, conventional-ish commit subjects: `feat(players): …`,
  `fix(sync): …`, `docs: …`, `refactor: …`, `test: …`.
- One logical change per PR. Include tests for new behaviour, update the README
  / `--help` when flags change, and add a line to
  [`CHANGELOG.md`](CHANGELOG.md) under **Unreleased**.
- Make sure `pytest` and `ruff check .` are green before opening the PR.

## Reporting issues

Open an issue with steps to reproduce, expected vs. actual behaviour, and your
**OS, Python version, terminal emulator, and player backend** (shown in the
visualizer's startup banner). For anything security-related, follow
[`SECURITY.md`](SECURITY.md) instead of filing a public issue.
