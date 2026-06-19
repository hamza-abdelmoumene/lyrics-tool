# lrc-tools

Terminal lyrics suite: fetch synced lyrics, process them into phrase- or
word-level timing, and render them live in the terminal as block letters,
synchronized to whatever your media player is playing (via `playerctl`/MPRIS).

Works with **Spotify** and with **local players** (mpv, VLC, rhythmbox, and any
other MPRIS-capable player) — the visualizer auto-follows whatever is currently
playing, or pin it with `--player`.

Three commands:

| Command         | What it does                                                        |
| --------------- | ------------------------------------------------------------------- |
| `lrc-fetch`     | Batch-download synced lyrics from LRCLIB / syncedlyrics.            |
| `lrc-processor` | Split long phrases; optionally convert to word-level (`.wlrc`).     |
| `lrc-vis`       | Live, terminal block-letter visualizer synced to the active player. |

## Features

- **Phrase and word-level sync** — `.lrc` (per line) and `.wlrc` (per word).
- **On-the-beat timing** — a built-in lead cancels the player's reported-position
  buffer lag and paint latency, so lines land *with* the vocal, not behind it.
  Tune further with `--offset` (positive = earlier).
- **Glitch track announce** — every track switch opens with a short glitch burst
  (band tears, scrambling letters, chromatic flicker) that resolves into the
  song-name card, then hands off to the lyrics ~1.2s later.
- **Cover-tinted UI** — the title card paints the terminal in the album cover's
  dominant colour (saturated, with text auto-set dark on light covers / light on
  dark ones), and the lyrics are tinted with a softer, desaturated accent of the
  same colour so they stay easy on the eyes. (Needs Pillow; disable with
  `--no-cover-color`.)
- **Auto-follow any player** — works with Spotify and local MPRIS players out of
  the box; auto-detects the active one, or pin it with `--player spotify` / `mpv`.
- **Ad break screen** — when Spotify plays an advert, the lyrics swap to a bored
  `( ¬_¬ )  …zZ` *ad break* card, then snap back to the next real track.
- **Floating music notes** — ambient notes drift up the screen behind the
  lyrics. Disable with `--no-notes`.
- **Responsive renderer** — block letters wrap across rows to fit the terminal,
  and fall back to plain wrapped text when the window is too small. Resizes live.
- **Diff rendering** — repaints only when the line, notes, or terminal size
  change, so a held line costs ~no CPU and never flickers.
- **Offline word mode** — if no `.wlrc` exists, word timing is derived in-memory
  from the cached `.lrc` (no network round-trip).
- **Custom fonts** — supply your own block-letter font via JSON.

## Supported systems

- **Linux** with an MPRIS-capable player. This is the target platform: lyric sync
  and cover art are read over MPRIS via `playerctl`.
- **Players:** Spotify (incl. ad detection) and any local MPRIS player — mpv, VLC,
  rhythmbox, etc. macOS/Windows are not supported (no `playerctl`/MPRIS).

## Requirements

- Python ≥ 3.9
- [`playerctl`](https://github.com/altdesktop/playerctl) — read the active player (MPRIS)
- A truecolor terminal — for the cover-tinted card and lyrics (most modern
  terminals; falls back gracefully without colour otherwise)
- `Pillow` — album-cover colour extraction (installed automatically)
- `ffmpeg` (`ffprobe`) — audio duration, for processing
- Optional: `librosa` + `numpy` (`pip install 'lrc-tools[onset]'`) for real per-word
  onset detection instead of even spacing

## Install

```bash
# Recommended: isolated install with pipx
pipx install .

# or a normal/editable install
pip install -e .            # add [dev] for tests, [onset] for librosa
```

This puts `lrc-vis`, `lrc-fetch`, and `lrc-processor` on your `PATH`.

> **Upgrading from an early build?** Cover colours need Pillow. If your pipx
> install predates that dependency, refresh it once with
> `pipx reinstall lrc-tools` (or `pipx inject lrc-tools Pillow`).

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
earlier). Lyrics for the playing track are fetched on the fly if not cached.

Handy shell aliases:

```sh
LRC=~/.local/share/lrc-tools/lyrics/processed
alias lyrics="lrc-vis --lrc-dir $LRC"                                  # phrase mode, full effects
alias lyrics-word="lrc-vis --lrc-dir $LRC --wlrc"                      # word mode
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

The pure logic (parsing, phrase→word conversion, rendering) is covered by tests
and runs without `playerctl`, audio, or network.

## Credits

Forked from `tacos-terminal-lyrics`; restructured into an installable package
with a responsive/diffed renderer, offline word-mode, and a test suite.

## License

MIT — see [LICENSE](LICENSE).
