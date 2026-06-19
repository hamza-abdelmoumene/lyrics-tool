# lyrics-tool

**The ultimate terminal lyrics suite: perfectly synced, cover-tinted, and beautifully animated.**

![Demo](https://raw.githubusercontent.com/hamza-abdel/lrc-tools/main/demo.gif)

## Features
- **Phrase and word-level sync** (`.lrc` and `.wlrc`).
- **Cover-tinted UI**: The terminal adapts to the album cover's dominant color.
- **Dynamic animations**: Glitch track announces, ad-break screens, and ambient floating notes.
- **Auto-follow**: Works with Spotify and local MPRIS players via `playerctl` out of the box.
- **Zero-lag rendering**: On-the-beat timing with a built-in lead to cancel buffer lag.
- **Reliable background fetching**: Fetches lyrics from LRCLIB on the fly without blocking the UI.

## Quickstart

Install `lyrics-tool` using `pipx` (recommended) or `pip`:
```bash
pipx install .
```

### Fetch Lyrics
```bash
lyrics-tool fetch --audio-dir ~/Music --output-dir ~/.local/share/lrc-tools/lyrics/raw
```

### Visualize (Live Sync)
Play a song in Spotify or mpv, then run:
```bash
lyrics-tool vis --lrc-dir ~/.local/share/lrc-tools/lyrics/raw
```

## Documentation
- [Usage Guide](docs/usage.md)
- [Configuration](docs/configuration.md)
- [LRC Format](docs/lrc-format.md)
- [Development](docs/development.md)

## Requirements
- Python ≥ 3.9
- Linux with `playerctl` installed.
- A truecolor terminal.

[![CI](https://github.com/hamza-abdel/lrc-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/hamza-abdel/lrc-tools/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
