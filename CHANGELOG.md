# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.2] — 2026-07-23

### Fixed
- **Auto-detect now follows the music that's actually playing.** With several
  MPRIS players alive at once, the visualizer could latch onto whatever sorted
  first by name — so a stopped chat-app voice message or a paused browser tab
  would hijack the panel from the track you were listening to. The player is now
  resolved by preferring a *Playing* source and breaking ties toward known music
  apps, instead of trusting `playerctl`'s name-ordered pick.
- Chat / telephony / meeting apps (Telegram, Discord, Signal, Slack, Zoom, …)
  join web browsers in the default ignore list, and ignore matching is now
  case-insensitive on the player's base name — previously `--ignore-player`
  matched case-sensitively, so a player registering with capitals slipped
  through. Pass `--ignore-player ''` to follow anything.

## [0.2.1] — 2026-07-22

### Added
- Album-art colour tinting on macOS (`nowplaying-cli` artwork) and best-effort on
  Windows (SMTC session thumbnail), in addition to Linux — written to a temp file
  the cover extractor reads like any other art source.
- **Distribution.** `lyrics-tool` is now installable from
  [PyPI](https://pypi.org/project/lyrics-tool/) (`pipx install lyrics-tool`) and
  the [AUR](https://aur.archlinux.org/packages/lyrics-tool) (`lyrics-tool` and
  `lyrics-tool-git`).

### Changed
- `release.yml` now always publishes a GitHub Release (with the sdist + wheel
  attached) on a `v*` tag; PyPI publishing is gated behind the `PUBLISH_TO_PYPI`
  repository variable so tagging never fails before it's configured.
- The GitHub Release step is now idempotent (create-or-upload with `--clobber`),
  so re-running a release tag refreshes its assets instead of failing.

## [0.2.0] — 2026-07-21

The cross-platform release: `lyricsooo` now follows your player on Linux,
Windows, and macOS through one pluggable backend layer.

### Added

- **Cross-platform now-playing backends.** A new `lyrics_tool.players` package
  abstracts the media source behind a single `NowPlaying` snapshot:
  - `playerctl` — Linux/BSD via MPRIS (the reference backend; full art support).
  - `smtc` — Windows via the System Media Transport Controls (`winsdk`,
    installed with the `[windows]` extra). Position is extrapolated from the
    session's last-update time so the sync clock tracks in real time.
  - `nowplaying-cli` — macOS via the `nowplaying-cli` helper.
  The right backend is auto-selected per OS; override with `--player-backend`
  or `$LYRICSOOO_PLAYER_BACKEND`. If none is available the offline tools still
  work and the visualizer shows its idle screen with a hint.
- **Cross-platform keyboard input** (`lyrics_tool.keyinput`): the live sync
  nudges and the `--select` picker now work on Windows (`msvcrt`) as well as
  POSIX, and the Windows console is switched into ANSI/VT mode automatically.
- **New line-reveal effects** `fade` (soft per-line fade-in) and `glow` (the
  active line gently breathes), selectable with `--reveal` or in `--select`.
- Windows and macOS install paths, an AUR `PKGBUILD` under `packaging/`, and a
  PyPI Trusted-Publishing release workflow.
- Project docs: `SECURITY.md`, `CODE_OF_CONDUCT.md`, this changelog, issue/PR
  templates, and Dependabot.

### Changed

- `visualizer_player` is now a thin, stable facade over the selected backend —
  its public API (`get_state`, `get_art_url`, `get_track_full`, `is_ad`,
  `PlayerState`, `set_player`, `set_ignored`) is unchanged.
- CI now runs the suite on Linux (Python 3.9–3.13) **and** Windows + macOS.
- README reframed as genuinely cross-platform, with a per-OS live-sync matrix
  and refreshed previews.

### Removed

- The `--cava` reactive spectrum frame and its external `cava` dependency, in
  favour of the pure-Python `fade`/`glow` reveals (portable, no subprocess).

### Security

- Untrusted lyric and track-metadata text is stripped of terminal control
  bytes (including `ESC`) before display, preventing ANSI-escape injection from
  crafted lyrics or titles. See [`SECURITY.md`](SECURITY.md).

## [0.1.0]

Initial public release.

- Three commands: `lyricsooo` (live block-letter visualizer), `lyricsooo-fetch`
  (batch LRCLIB download), `lyricsooo-cook` (phrase/word preparation).
- Phrase- and word-level (`.lrc` / `.wlrc`) sync with a phase-locked playback
  clock, diff rendering, floating notes, glitch track-announce, ad-break screen,
  and typewriter reveal.
- Universal, pluggable colour sources (album art, pywal, caelestia, matugen,
  `fixed:`/`file:`), zero-config XDG data directories, and a stubbed-player test
  suite that runs with no playerctl, audio, or network.

[Unreleased]: https://github.com/hamza-abdelmoumene/lyrics-tool/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/hamza-abdelmoumene/lyrics-tool/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/hamza-abdelmoumene/lyrics-tool/releases/tag/v0.2.0
[0.1.0]: https://github.com/hamza-abdelmoumene/lyrics-tool/tree/1ec0fbf
