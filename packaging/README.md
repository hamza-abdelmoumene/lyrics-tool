# Packaging

`lyrics-tool` is a pure-Python package, so the universal install paths (`pipx`,
`uv`, `pip`) work on **every distro and OS** with no packaging work at all — see
the [Installation section of the README](../README.md#installation). The files
here are for maintainers who want native distro packages on top of that.

| File | Target | Status |
| ---- | ------ | ------ |
| [`aur/PKGBUILD`](aur/PKGBUILD) | Arch Linux (AUR) | Template — builds from the GitHub release tag |
| [`homebrew/lyrics-tool.rb`](homebrew/lyrics-tool.rb) | macOS / Linuxbrew | Template — isolated virtualenv install |
| [`../.github/workflows/release.yml`](../.github/workflows/release.yml) | PyPI | Ready — Trusted Publishing on a `v*` tag |

## Cutting a release (PyPI)

1. Bump the version in `pyproject.toml` **and** `src/lyrics_tool/__init__.py`, and
   add a section to [`CHANGELOG.md`](../CHANGELOG.md).
2. Tag and push:
   ```bash
   git tag -a v0.2.0 -m "v0.2.0" && git push origin v0.2.0
   ```
   `release.yml` builds the sdist + wheel, runs `twine check`, and **publishes a
   GitHub Release** with them attached. This always works — no secrets needed.

### Enabling PyPI (one-time, optional)

PyPI publishing is gated so tagging never fails before it's configured:

1. Register `lyrics-tool` as a
   [Trusted Publisher](https://docs.pypi.org/trusted-publishers/) on PyPI,
   pointing at `release.yml` in this repo (environment `pypi`).
2. Add a repository variable **`PUBLISH_TO_PYPI` = `true`**
   (Settings → Secrets and variables → Actions → Variables).

From then on, every `v*` tag also publishes to PyPI via short-lived OIDC (no API
token stored anywhere), and `pipx install lyrics-tool` / `uv tool install
lyrics-tool` work everywhere.

## AUR notes

- After bumping `pkgver`, run `updpkgsums` to pin the source checksum and
  `makepkg --printsrcinfo > .SRCINFO` before pushing to the AUR.
- `python-syncedlyrics` may only be available from the AUR; the rest of the
  runtime dependencies are in the official repositories.

## Homebrew notes

- Point `url`/`sha256` at the release tarball (or the PyPI sdist).
- Run `brew update-python-resources Formula/lyrics-tool.rb` to pin each Python
  dependency as a `resource` block for a reproducible bottle.
