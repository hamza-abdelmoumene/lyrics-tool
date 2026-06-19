# lrc-tools

Terminal lyrics suite: fetch synced lyrics, process them into phrase- or
word-level timing, and render them live in the terminal as block letters,
synchronized to whatever your media player is playing (via `playerctl`/MPRIS).

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
- **Cover-tinted song card** — on every track switch the song-name card paints
  the terminal in the album cover's dominant colour, with text auto-set to white
  on dark covers and dark on light ones. Lyrics then return to the default
  terminal colours. (Needs Pillow; disable with `--no-cover-color`.)
- **Floating music notes** — ambient notes drift up the screen behind the
  lyrics. Disable with `--no-notes`.
- **Responsive renderer** — block letters wrap across rows to fit the terminal,
  and fall back to plain wrapped text when the window is too small. Resizes live.
- **Diff rendering** — repaints only when the line, notes, or terminal size
  change, so a held line costs ~no CPU and never flickers.
- **Offline word mode** — if no `.wlrc` exists, word timing is derived in-memory
  from the cached `.lrc` (no network round-trip).
- **Custom fonts** — supply your own block-letter font via JSON.

## Requirements

- Python ≥ 3.9
- [`playerctl`](https://github.com/altdesktop/playerctl) — read the active player (MPRIS)
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

## Usage

```bash
# 1. Fetch lyrics for your library
lrc-fetch --audio-dir ~/Music --output-dir ~/.local/share/lrc-tools/lyrics/raw

# 2. Process: split long phrases (add --wlrc for word-level)
lrc-processor \
  --lrc-dir ~/.local/share/lrc-tools/lyrics/raw \
  --output-dir ~/.local/share/lrc-tools/lyrics/processed \
  --no-require-audio

# 3. Visualize, synced to the current track
lrc-vis --lrc-dir ~/.local/share/lrc-tools/lyrics/processed          # phrase mode
lrc-vis --lrc-dir ~/.local/share/lrc-tools/lyrics/processed --wlrc   # word mode
```

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
