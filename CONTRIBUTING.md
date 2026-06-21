# Contributing to lyrics-tool

Thanks for your interest in contributing! Here's how to get started.

## Prerequisites

- **Python ≥ 3.9**
- **[playerctl](https://github.com/altdesktop/playerctl)** — for MPRIS integration (testing the visualizer live)
- **ffmpeg** (`ffprobe`) — for audio duration detection in the processor

## Development Setup

```bash
# Clone the repo
git clone https://github.com/hamza-abdelmoumene/lyrics-tool.git
cd lyrics-tool

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in editable mode with dev dependencies
pip install -e '.[dev]'
```

This registers the `lyricsooo`, `lyricsooo-fetch`, and `lyricsooo-cook` commands
in your virtual environment.

## Running Tests

```bash
# Run the full test suite
python -m pytest

# Run with verbose output
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_visualizer.py -v
```

All tests run without `playerctl`, audio files, or network access — the
visualizer loop is driven with a stubbed player.

## Code Style

- Keep functions focused and well-documented.
- Preserve existing docstrings and comments when modifying code.
- Use type hints where practical.
- Follow the existing patterns in the codebase (e.g. `RGB` tuples, `_paint()`
  diff rendering, lock-free `SyncData`).

## Submitting Changes

1. **Fork** the repository and create a feature branch from `main`.
2. **Write tests** for any new functionality.
3. **Run the test suite** — all tests must pass.
4. **Open a pull request** with a clear description of the change.

## Reporting Issues

Open an issue on
[GitHub](https://github.com/hamza-abdelmoumene/lyrics-tool/issues) with:

- Steps to reproduce
- Expected vs actual behaviour
- Your Python version and terminal emulator
