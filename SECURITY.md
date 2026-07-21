# Security Policy

## Supported versions

`lyrics-tool` is released from `main`. Security fixes land on the latest minor
series and ship in the next patch release.

| Version | Supported |
| ------- | --------- |
| 0.2.x   | ✅        |
| < 0.2   | ❌        |

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through GitHub:

1. Go to the repository's **Security** tab → **Report a vulnerability**
   ([private advisory form](https://github.com/hamza-abdelmoumene/lyrics-tool/security/advisories/new)).
2. Or email the maintainer at **ph_abdelmoumene@esi.dz** with the details.

Please include a description, reproduction steps, the affected version, and your
platform. You can expect an acknowledgement within **7 days** and, for a
confirmed issue, a fix or mitigation plan before any public disclosure. We'll
credit you in the advisory unless you'd rather stay anonymous.

## Security model

`lyrics-tool` is a local, single-user terminal application. It has **no server,
no telemetry, no accounts, and needs no elevated privileges**. Still, it handles
data from the network and talks to other programs, so here's what it does and
the boundaries it enforces:

- **Untrusted lyric & metadata text.** Lyrics come from the network (LRCLIB and
  the `syncedlyrics` providers) and track metadata comes from your media player.
  All of it is treated as untrusted: control bytes — including the `ESC` that
  begins every ANSI sequence — are stripped before anything is written to the
  terminal (`visualizer_display.sanitize_text`), so a crafted lyric or title
  can't inject cursor moves, colour, or screen-clearing escapes.
- **Subprocesses, never a shell.** The visualizer invokes `playerctl` (Linux),
  `nowplaying-cli` (macOS), and `ffprobe` (optional) by fixed program name using
  argument **lists** — `shell=True` is never used — so player names, file paths,
  and other values can't inject shell commands. Every call has a short timeout.
- **Network access.** Outbound HTTPS to lyric providers, plus fetching the
  album-art image URL your player advertises (for the colour tint). No data is
  ever sent about you; requests carry only the track's artist/title/album.
- **Filesystem.** Reads only the audio directories you point it at; writes only
  the lyric cache and a small sync-offset file under your XDG data/state dirs
  (`~/.local/share/lyrics-tool`, `~/.local/state/lyrics-tool`).

## Dependencies

Runtime dependencies are pinned by lower bound in `pyproject.toml` and updated
via Dependabot. The optional `[onset]` (librosa) and `[windows]` (winsdk) extras
are only pulled in when you ask for them.
