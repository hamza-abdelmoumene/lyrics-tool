# Usage Guide

`lyrics-tool` consists of three main commands: `fetch`, `process`, and `vis`.

## 1. Fetching Lyrics
Batch-download lyrics for your local audio files.

```bash
lyrics-tool fetch --audio-dir ~/Music --output-dir ~/.local/share/lrc-tools/lyrics/raw
```

## 2. Processing Lyrics
Split long phrases or convert LRC to WLRC.

```bash
lyrics-tool process \
  --lrc-dir ~/.local/share/lrc-tools/lyrics/raw \
  --output-dir ~/.local/share/lrc-tools/lyrics/processed \
  --wlrc
```

## 3. Visualizing Lyrics
Sync lyrics in your terminal to your active media player.

```bash
lyrics-tool vis --lrc-dir ~/.local/share/lrc-tools/lyrics/processed
```
