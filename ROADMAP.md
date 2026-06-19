# Roadmap

## High Priority
- Add support for Spotify via the `dbus` API directly on Linux to fetch lyrics when `playerctl` is unavailable or out-of-sync.
- Implement an automatic fallback to word-level approximation if the fetched lyrics from LRCLIB are missing WLRC timestamps.

## Medium Priority
- Create an interactive setup wizard (`lyrics-tool init`) for initial configurations and path setups.
- Add macOS support by integrating with native now-playing APIs.

## Low Priority
- Windows support through Windows Media APIs.
- Built-in UI themes for visualizer configuration.
