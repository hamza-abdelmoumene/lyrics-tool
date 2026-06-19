# lrc-tools

Terminal lyrics suite: fetch synced lyrics, process them into phrase- or
word-level timing, and render them live in the terminal as block letters,
synchronized to whatever your media player is playing (via `playerctl`/MPRIS).

Works with **Spotify** and with **local players** (mpv, VLC, rhythmbox, and any
other MPRIS-capable player) — the visualizer auto-follows whatever is currently
playing, or pin it with `--player`.

## Previews

| Feature & Description | Visual Preview |
| :--- | :--- |
| **Terminal Lyrics Visualizer** <br><br> The core visualizer rendering block-letter lyrics in the terminal. Features custom fonts, dynamic resizing, and real-time player synchronization. | <img src="https://raw.githubusercontent.com/hamza-abdelmoumene/lrc-tools/main/assets/image-preview.gif" width="450" alt="Terminal Lyric Visualizer" /> |
| **Phrase-Level Playback** <br><br> Seamlessly tracks playing songs line-by-line, matching vocal delivery exactly. Uses a custom timing offset to eliminate player lag. | <img src="https://raw.githubusercontent.com/hamza-abdelmoumene/lrc-tools/main/assets/song-phrase-preview.gif" width="450" alt="Phrase-level lyric rendering & visualizer" /> |
| **Smooth Glitch Transitions** <br><br> A high-performance scrambler effect that triggers on track change, rendering a scrambled/glitched text banner before resolving into the album info card. | <img src="https://raw.githubusercontent.com/hamza-abdelmoumene/lrc-tools/main/assets/switching-preview.gif" width="450" alt="Smooth track switching glitch & banner" /> |
| **Dynamic Color Tinting** <br><br> Extracts the dominant vibrant color from the album artwork, adapting the terminal background and lyric colors to fit the song's aesthetic. | <img src="https://raw.githubusercontent.com/hamza-abdelmoumene/lrc-tools/main/assets/colors-preview.png" width="450" alt="Dynamic cover-art color-tinted theme" /> |
| **Animated Ad-Break Screen** <br><br> Automatically detects when Spotify or local players play an advertisement, displaying an animated idle card and resuming lyrics immediately on the next song. | <img src="https://raw.githubusercontent.com/hamza-abdelmoumene/lrc-tools/main/assets/ads-preview.gif" width="450" alt="Animated ad break screen" /> |

## Commands

Three commands:

| Command         | What it does                                                        |
| --------------- | ------------------------------------------------------------------- |
| `lrc-fetch`     | Batch-download synced lyrics from LRCLIB / syncedlyrics.            |
| `lrc-processor` | Split long phrases; optionally convert to word-level (`.wlrc`).     |
| `lrc-vis`       | Live, terminal block-letter visualizer synced to the active player. |

## Features

- **Phrase and word-level sync** — `.lrc` (per line) and `.wlrc` (per word).
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



## Footprint

It's light — it's a sleep-driven loop, not a busy renderer. The diff renderer
only repaints when the lyric line, the notes, or the terminal size actually
change, and playback position is extrapolated from the monotonic clock instead
of polling the player every frame.

Measured on Linux / CPython 3.14, one `lrc-vis` process during continuous
playback (lyrics flipping + floating notes):

| Metric | Idle / paused | 80×24 terminal | Large terminal (≈200×50) |
| ------ | ------------- | -------------- | ------------------------ |
| Memory (RSS) | ~30 MiB | ~33 MiB | ~33 MiB |
| CPU | ~0% | ~1% of one core | ~3% of one core |

CPU scales with terminal size (more cells → more floating notes) and with
`--refresh-rate`; memory is flat (lyrics and cover colours are cached, not
accumulated). `--no-notes` trims the steady-state CPU further. Numbers are
approximate and hardware-dependent.

## Installation & Requirements

The suite contains three main utilities: `lrc-fetch`, `lrc-processor`, and the live visualizer `lrc-vis`. Follow the setup instructions below for your specific operating system.

### 🐧 Linux (Full Native Support)

Linux is the target platform for `lrc-tools`. Both the offline CLI utilities and the live visualizer work natively out of the box.

#### 1. System Dependencies
Install `playerctl` (for player synchronization) and `ffmpeg` (for processing audio durations):

*   **Ubuntu / Debian:**
    ```bash
    sudo apt update
    sudo apt install playerctl ffmpeg
    ```
*   **Arch Linux:**
    ```bash
    sudo pacman -S playerctl ffmpeg
    ```
*   **Fedora:**
    ```bash
    sudo dnf install playerctl -y && sudo dnf install ffmpeg -y
    ```

#### 2. Python Package Installation
Using [`pipx`](https://github.com/pypa/pipx) is highly recommended to prevent dependency conflicts:
```bash
# Recommended installation
pipx install .

# Or install editable/locally using pip
pip install -e .
```
For optional high-accuracy word-level onset detection using librosa, install with:
```bash
pipx install .[onset]
# or: pip install -e '.[onset]'
```

---

### 🍏 macOS (CLI Tools Only / No Live Sync)

On macOS, you can fully use `lrc-fetch` and `lrc-processor` to manage and process your lyrics database. However, because macOS lacks Linux MPRIS support, the live visualizer `lrc-vis` cannot sync to your local media players.

#### 1. System Dependencies
Install `ffmpeg` via Homebrew:
```bash
brew install ffmpeg
```

#### 2. Python Package Installation
Install the suite via `pipx` or `pip`:
```bash
pipx install .
```

---

### 🪟 Windows (WSL for Full Support / Native for CLI Only)

Windows users have two ways to run `lrc-tools`:

#### Option A: Windows Subsystem for Linux (WSL) — *Recommended for Full Support*
By running inside WSL (Ubuntu, Arch, etc.), you get full visualizer capabilities.
1. Install WSL from your terminal: `wsl --install`
2. Follow the **Linux** installation instructions above within your WSL environment.
3. *Note:* Make sure your media player is running or accessible from the WSL terminal namespace.

#### Option B: Native Windows Command Prompt/PowerShell — *CLI Tools Only*
1. Download and install Python (ensure you check "Add Python to PATH").
2. Download and install `ffmpeg` and add it to your System PATH environment variables.
3. Install the suite from the project directory:
   ```powershell
   pip install .
   ```
4. Use `lrc-fetch` and `lrc-processor` to download and convert your lyrics.

---

### 💡 General Requirements & Tips
*   **Terminal Color Support:** A truecolor (24-bit) terminal with UTF-8 support is required to render the cover art tinting and block letters correctly (e.g., Alacritty, Kitty, GNOME Terminal, WezTerm, Windows Terminal).
*   **Album Cover Tinting:** Album cover color extraction requires the `Pillow` library, which is automatically installed as a dependency.

This puts `lrc-vis`, `lrc-fetch`, and `lrc-processor` on your `PATH`.

> **Upgrading from an early build?** Cover colors need Pillow. If your pipx install predates that dependency, refresh it once with `pipx reinstall lrc-tools` (or `pipx inject lrc-tools Pillow`).

## Usage

```bash
# 1. Fetch lyrics for your library
lrc-fetch --audio-dir ~/Music --output-dir ~/.local/share/lrc-tools/lyrics/raw

# 2. Process: split long phrases (add --wlrc for word-level)
lrc-processor \
  --lrc-dir ~/.local/share/lrc-tools/lyrics/raw \
  --output-dir ~/.local/share/lrc-tools/lyrics/processed \
  --no-require-audio

# 3. Visualize, synced to the current track (auto-follows the active player)
lrc-vis --lrc-dir ~/.local/share/lrc-tools/lyrics/processed          # phrase mode
lrc-vis --lrc-dir ~/.local/share/lrc-tools/lyrics/processed --wlrc   # word mode
lrc-vis --lrc-dir ... --player spotify   # pin to one player (e.g. spotify, mpv, vlc)
```

Useful flags: `--player <name>` to pin a player, `--no-cover-color` /
`--no-notes` to strip effects, `--offset <sec>` to nudge sync (positive =
earlier), `--banner-hold <sec>` to set how long the title card lingers (default
1.5). Lyrics for the playing track are fetched on the fly (in the background) if
not cached.

Handy shell aliases:

```sh
LRC=~/.local/share/lrc-tools/lyrics/processed
alias lyrics="lrc-vis --lrc-dir $LRC"                                  # phrase mode, full effects
alias lyrics-word="lrc-vis --lrc-dir $LRC --wlrc"                      # word mode
alias lyrics-typewriter="lrc-vis --lrc-dir $LRC --typewriter"          # typewriter effect
alias lyrics-plain="lrc-vis --lrc-dir $LRC --no-cover-color --no-notes"  # bare, no tint/notes
```

Press `Ctrl+C` to exit the visualizer.

## Configuration

Processing defaults can be set in a YAML file (see `src/lrc_tools/config_example.yaml`)
and passed with `--config path/to/config.yaml`. CLI flags override the file.

## Development

```bash
pip install -e '.[dev]'
python -m pytest            # or: python -m unittest discover -s tests
```

Tests cover the pure logic (parsing, phrase→word conversion, rendering, the
ambient note field) and the visualizer loop itself — driven with a stubbed
player so it asserts track announces, graceful no-lyrics handling, and that a
slow lyric fetch never blocks the display. Everything runs without `playerctl`,
audio, or network.

## Credits

Forked from `tacos-terminal-lyrics`; restructured into an installable package
with a responsive/diffed renderer, offline word-mode, and a test suite.

## License

MIT — see [LICENSE](LICENSE).
