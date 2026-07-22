# Homebrew

The Homebrew formula lives in its own tap, which is the source of truth:

**https://github.com/hamza-abdelmoumene/homebrew-tap** → `Formula/lyrics-tool.rb`

Install:

```sh
brew install hamza-abdelmoumene/tap/lyrics-tool
```

The tap builds the formula from source on macOS + Linux in CI on every push.
See [`../README.md`](../README.md#homebrew-notes) for how to refresh it on a new
release.
