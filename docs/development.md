# Development Guide

## Architecture Overview

`lyrics-tool` consists of several decoupled packages:
- `api/`: Interfaces with network services like LRCLIB.
- `parser/`: Parsing and conversion logic for LRC/WLRC files.
- `render/`: Terminal UI rendering logic including typography and colors.
- `sync/`: Logic to track audio state and timestamp math.
- `cli/`: Command-line interfaces.

## Scripts
- Run linter: `ruff check .`
- Run type checker: `mypy src`
- Run tests: `pytest tests/`
