<div align="center">

# lyricsooo

**Live, synced song lyrics — rendered as block letters right in your terminal.**

[![CI](https://github.com/hamza-abdelmoumene/lyrics-tool/actions/workflows/ci.yml/badge.svg)](https://github.com/hamza-abdelmoumene/lyrics-tool/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](pyproject.toml)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20WSL-lightgrey.svg)](#installation)

</div>

`lyrics-tool` is a small suite that **fetches** synced lyrics, **prepares** them
into phrase- or word-level timing, and **renders** them live in the terminal as
block letters, synchronized to whatever your media player is playing (via
`playerctl` / MPRIS).

Works with **Spotify** and with **local players** (mpv, VLC, rhythmbox, and any
other MPRIS-capable player) — the visualizer auto-follows whatever is currently
playing, or pin it with `--player`.

---

## Contents

- [Quick start](#quick-start)
- [The three commands](#the-three-commands)
- [Previews](#previews)
- [Features](#features)
- [Installation](#installation)
- [How your lyrics are stored](#how-your-lyrics-are-stored)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)
- [Footprint](#footprint)
- [Configuration](#configuration)
- [Development](#development)
- [Uninstall](#uninstall)

---

## Quick start

Once installed (see [Installation](#installation)), there is **nothing to
configure** — every command falls back to a shared default location under
`~/.local/share/lyrics-tool/`, so the whole flow works with zero flags:

```bash
lyricsooo-fetch --audio-dir ~/Music   # 1. download synced lyrics for your library
lyricsooo-cook                         # 2. prepare them (split long lines, etc.)
lyricsooo                              # 3. play — synced to your current track
```

Or skip steps 1–2 entirely: just run **`lyricsooo`** and start playing music.
Missing lyrics are fetched and cached **on the fly** as each track plays.

```bash
lyricsooo            # just works — fetches lyrics live as songs play
```

---

## The three commands

| Command           | What it does                                                          |
| ----------------- | -------------------------------------------------------------------- |
| `lyricsooo`       | Live, terminal block-letter visualizer synced to the active player.  |
| `lyricsooo-fetch` | Batch-download synced lyrics from LRCLIB / syncedlyrics.              |
| `lyricsooo-cook`  | Split long phrases; optionally convert to word-level (`.wlrc`).      |

Every command supports `--help`.

## Previews

| Feature & Description | Visual Preview |
| :--- | :--- |
| **Terminal Lyrics Visualizer** <br><br> The core visualizer rendering block-letter lyrics in the terminal. Features custom fonts, dynamic resizing, and real-time player synchronization. | <img src="https://raw.githubusercontent.com/hamza-abdelmoumene/lyrics-tool/main/assets/image-preview.gif" width="450" alt="Terminal Lyric Visualizer" /> |
| **Phrase-Level Playback** <br><br> Seamlessly tracks playing songs line-by-line, matching vocal delivery exactly. Uses a custom timing offset to eliminate player lag. | <img src="https://raw.githubusercontent.com/hamza-abdelmoumene/lyrics-tool/main/assets/song-phrase-preview.gif" width="450" alt="Phrase-level lyric rendering & visualizer" /> |
| **Smooth Glitch Transitions** <br><br> A high-performance scrambler effect that triggers on track change, rendering a scrambled/glitched text banner before resolving into the album info card. | <img src="https://raw.githubusercontent.com/hamza-abdelmoumene/lyrics-tool/main/assets/switching-preview.gif" width="450" alt="Smooth track switching glitch & banner" /> |
| **Dynamic Color Tinting** <br><br> Extracts the dominant vibrant color from the album artwork, adapting the terminal background and lyric colors to fit the song's aesthetic. | <img src="https://raw.githubusercontent.com/hamza-abdelmoumene/lyrics-tool/main/assets/colors-preview.png" width="450" alt="Dynamic cover-art color-tinted theme" /> |
| **Animated Ad-Break Screen** <br><br> Automatically detects when Spotify or local players play an advertisement, displaying an animated idle card and resuming lyrics immediately on the next song. | <img src="https://raw.githubusercontent.com/hamza-abdelmoumene/lyrics-tool/main/assets/ads-preview.gif" width="450" alt="Animated ad break screen" /> |

## Features

- **Phrase and word-level sync** — `.lrc` (per line) and `.wlrc` (per word).
- **Zero-config defaults** — all three commands share a standard data directory,
  so the common workflow needs no path flags.
- **Typewriter mode** — progressive character reveal with a blinking cursor.
- **On-the-beat timing** — a built-in lead cancels the player's reported-position
  buffer lag and paint latency, so lines land *with* the vocal, not behind it.
  Tune further with `--offset` (positive = earlier).
- **Glitch track announce** — every track switch opens with a short glitch burst
  (band tears, scrambling letters, chromatic flicker) that resolves into the
  song-name card. The settled card is held for a guaranteed window (`--banner-hold`,
  default 1.5s, timed *after* the glitch) so it never flashes past, then hands
  off to the lyrics.
- **Never blocks on the network** — lyrics for the playing track are fetched on
  the fly in the background, so the display stays responsive and track switches
  register instantly even while a download is in flight. While it searches you
  get an animated *finding lyrics* screen; if a song genuinely has none, it
  settles into a calm *no synced lyrics* idle screen instead of freezing.
- **Cover-tinted UI** — the title card paints the terminal in the album cover's
  dominant colour (saturated, with text auto-set dark on light covers / light on
  dark ones), and the lyrics are tinted with a softer, desaturated accent of the
  same colour so they stay easy on the eyes. (Needs Pillow; disable with
  `--no-cover-color`.)
- **Auto-follow any player** — works with Spotify and local MPRIS players out of
  the box; auto-detects the active one, or pin it with `--player spotify` / `mpv`.
- **Ad break screen** — when Spotify plays an advert, the lyrics swap to an
  animated *ad break* card — a bored face that cycles with a drifting snooze
  trail over the music notes — then snaps back to the next real track.
- **Floating music notes** — ambient notes drift up the screen behind the
  lyrics, the idle screens, and the ad card. Disable with `--no-notes`.
- **Responsive renderer** — block letters wrap across rows to fit the terminal,
  and fall back to plain wrapped text when the window is too small. Resizes live.
- **Diff rendering** — repaints only when the line, notes, or terminal size
  change, so a held line costs ~no CPU and never flickers.
- **Offline word mode** — if no `.wlrc` exists, word timing is derived in-memory
  from the cached `.lrc` (no network round-trip).
- **Custom fonts** — supply your own block-letter font via JSON.

## Installation

### Prerequisites

| Requirement | Why | Notes |
| ----------- | --- | ----- |
| **Python ≥ 3.9** | runs the suite | `python3 --version` |
| **`pipx`** | clean isolated install | recommended over bare `pip` |
| **`playerctl`** | live player sync (the visualizer) | Linux / WSL only |
| **`ffmpeg`** (`ffprobe`) | read audio durations when processing | optional but recommended |
| **truecolor terminal + UTF-8** | block letters & cover tinting | Kitty, Alacritty, WezTerm, GNOME Terminal, Windows Terminal, … |

> `Pillow` (album-cover colour extraction) is installed automatically as a
> Python dependency — no system package needed.

---

### Linux — full native support

Linux is the primary platform. Both the offline CLI utilities and the live
visualizer work out of the box.

**Step 1 — system dependencies**

<details open>
<summary><strong>Ubuntu / Debian</strong></summary>

```bash
sudo apt update
sudo apt install -y playerctl ffmpeg pipx
pipx ensurepath          # adds ~/.local/bin to your PATH
```
> On Ubuntu 22.04 or older, `pipx` may be unavailable via apt. Install it with
> `python3 -m pip install --user pipx && python3 -m pipx ensurepath` instead.
</details>

<details>
<summary><strong>Arch Linux</strong></summary>

```bash
sudo pacman -S --needed playerctl ffmpeg python-pipx
pipx ensurepath
```
</details>

<details>
<summary><strong>Fedora</strong></summary>

```bash
sudo dnf install -y playerctl ffmpeg pipx
pipx ensurepath
```
</details>

**Step 2 — install lyrics-tool**

```bash
git clone https://github.com/hamza-abdelmoumene/lyrics-tool.git
cd lyrics-tool
pipx install .
```

**Step 3 — open a new terminal** (so the updated `PATH` from `pipx ensurepath`
takes effect), then verify:

```bash
lyricsooo --help
```

You should see the help for the visualizer. The commands `lyricsooo`,
`lyricsooo-fetch`, and `lyricsooo-cook` are now on your `PATH`.

> **Optional — high-accuracy word timing.** Per-word onset detection uses
> `librosa`. It's heavy, so it's an opt-in extra:
> ```bash
> pipx install '.[onset]'
> ```

---

### macOS — CLI tools only (no live sync)

`lyricsooo-fetch` and `lyricsooo-cook` work fully, but macOS has no MPRIS, so the
live visualizer `lyricsooo` **cannot** follow local players.

```bash
brew install ffmpeg pipx
pipx ensurepath
git clone https://github.com/hamza-abdelmoumene/lyrics-tool.git
cd lyrics-tool
pipx install .
```

---

### Windows

**Recommended — WSL (full support).** Inside WSL (Ubuntu/Arch/…) you get the full
visualizer:

```powershell
wsl --install        # then open your WSL distro and follow the Linux steps above
```

Make sure your media player is reachable from the WSL session.

**Native Windows — CLI tools only.** No MPRIS, so no live visualizer:

1. Install Python (tick *"Add Python to PATH"*).
2. Install `ffmpeg` and add it to your `PATH`.
3. From the cloned project folder: `pip install .`
4. Use `lyricsooo-fetch` and `lyricsooo-cook` to download and prepare lyrics.

---

### Editable / development install

```bash
pip install -e '.[dev]'
```

> **Upgrading from an early build?** Cover colours need Pillow. If your pipx
> install predates that dependency, refresh it once with
> `pipx reinstall lyrics-tool` (or `pipx inject lyrics-tool Pillow`).

## How your lyrics are stored

Unless you pass explicit `--*-dir` flags, everything lives under one root
(honouring `$XDG_DATA_HOME`):

```
~/.local/share/lyrics-tool/
└── lyrics/
    ├── raw/         # lyricsooo-fetch downloads here  →  also lyricsooo-cook's input
    └── processed/   # lyricsooo-cook writes here      →  lyricsooo reads here
```

The visualizer also caches lyrics it fetches on the fly into `processed/`. These
directories are **created automatically** the first time they're needed — you
never have to `mkdir` anything.

## Usage

The zero-flag flow (see [Quick start](#quick-start)) covers most uses. Full form
with explicit directories:

```bash
# 1. Fetch lyrics for your library
lyricsooo-fetch --audio-dir ~/Music

# 2. Prepare: split long phrases (add --wlrc for word-level)
lyricsooo-cook --no-require-audio

# 3. Visualize, synced to the current track (auto-follows the active player)
lyricsooo                       # phrase mode
lyricsooo --wlrc                # word mode
lyricsooo --player spotify      # pin to one player (e.g. spotify, mpv, vlc)
```

Useful flags: `--player <name>` to pin a player, `--no-cover-color` /
`--no-notes` to strip effects, `--offset <sec>` to nudge sync (positive =
earlier), `--banner-hold <sec>` to set how long the title card lingers (default
1.5), `--typewriter` for the character-reveal effect.

Optional shell aliases (the defaults already make these short, but if you like):

```sh
alias lyrics="lyricsooo"                               # phrase mode, full effects
alias lyrics-word="lyricsooo --wlrc"                   # word mode
alias lyrics-typewriter="lyricsooo --typewriter"       # typewriter effect
alias lyrics-plain="lyricsooo --no-cover-color --no-notes"  # bare, no tint/notes
```

Press `Ctrl+C` to exit the visualizer.

## Troubleshooting

| Symptom | Cause & fix |
| ------- | ----------- |
| `lyricsooo: command not found` | `pipx`'s bin dir isn't on your `PATH`. Run `pipx ensurepath`, then **open a new terminal**. |
| `Error: LRC directory … does not exist` | You passed an explicit `--lrc-dir` that doesn't exist (typo). Drop the flag to use the default, or create/point at a real folder. Running `lyricsooo` with **no** `--lrc-dir` creates the default directory for you. |
| Lyrics don't move / no sync | The visualizer needs `playerctl` and a running MPRIS player. Check `playerctl metadata` returns something; try pinning with `--player spotify`. |
| `no synced lyrics` for a track | That song has no synced lyrics on LRCLIB. Nothing to fix — playback continues normally. |
| Block letters look like boxes / no colour | Use a truecolor, UTF-8 terminal (Kitty, Alacritty, WezTerm, …). |
| Cover tint missing | `Pillow` not installed — `pipx inject lyrics-tool Pillow`. |
| `ffprobe: not found` when processing | Install `ffmpeg`, or run `lyricsooo-cook --no-require-audio` to skip duration lookups. |

## Footprint

It's light — a sleep-driven loop, not a busy renderer. The diff renderer only
repaints when the lyric line, the notes, or the terminal size actually change,
and playback position is extrapolated from the monotonic clock instead of
polling the player every frame.

Measured on Linux / CPython 3.14, one `lyricsooo` process during continuous
playback (lyrics flipping + floating notes):

| Metric | Idle / paused | 80×24 terminal | Large terminal (≈200×50) |
| ------ | ------------- | -------------- | ------------------------ |
| Memory (RSS) | ~30 MiB | ~33 MiB | ~33 MiB |
| CPU | ~0% | ~1% of one core | ~3% of one core |

CPU scales with terminal size (more cells → more floating notes) and with
`--refresh-rate`; memory is flat (lyrics and cover colours are cached, not
accumulated). `--no-notes` trims the steady-state CPU further. Numbers are
approximate and hardware-dependent.

## Configuration

Processing defaults can be set in a YAML file (see
[`src/lyrics_tool/config_example.yaml`](src/lyrics_tool/config_example.yaml)) and
passed with `--config path/to/config.yaml`. CLI flags override the file.

## Development

```bash
pip install -e '.[dev]'
python -m pytest            # or: python -m unittest discover -s tests
ruff check src tests        # lint
```

Tests cover the pure logic (parsing, phrase→word conversion, rendering, the
ambient note field) and the visualizer loop itself — driven with a stubbed
player so it asserts track announces, graceful no-lyrics handling, and that a
slow lyric fetch never blocks the display. Everything runs without `playerctl`,
audio, or network.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution workflow.

## Uninstall

```bash
pipx uninstall lyrics-tool
rm -rf ~/.local/share/lyrics-tool      # remove cached lyrics (optional)
```

## Credits

Forked from `tacos-terminal-lyrics`; restructured into an installable package
with a responsive/diffed renderer, offline word-mode, and a test suite.

## License

MIT — see [LICENSE](LICENSE).
