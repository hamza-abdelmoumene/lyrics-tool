# Packaging

`lyrics-tool` is a pure-Python package, so the universal install paths (`pipx`,
`uv`, `pip`) work on **every distro and OS** with no packaging work at all — see
the [Installation section of the README](../README.md#installation). The files
here are for maintainers who want native distro packages on top of that.

| File | Target | Status |
| ---- | ------ | ------ |
| [`aur/PKGBUILD`](aur/PKGBUILD) | Arch Linux (AUR) | **Published** → [`lyrics-tool`](https://aur.archlinux.org/packages/lyrics-tool) — builds from the release tag |
| [`aur-git/PKGBUILD`](aur-git/PKGBUILD) | Arch Linux (AUR) | **Published** → [`lyrics-tool-git`](https://aur.archlinux.org/packages/lyrics-tool-git) — builds from `main` |
| [`homebrew/`](homebrew/) → [homebrew-tap](https://github.com/hamza-abdelmoumene/homebrew-tap) | macOS / Linuxbrew | **Published** → `brew install hamza-abdelmoumene/tap/lyrics-tool` |
| [`../.github/workflows/release.yml`](../.github/workflows/release.yml) | PyPI | **Published** → [`lyrics-tool`](https://pypi.org/project/lyrics-tool/) — auto-publishes on every `v*` tag (Trusted Publishing) |

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

Both packages are already published (`lyrics-tool`, `lyrics-tool-git`). **On every
new release, update the AUR** — the git one auto-follows `main`, but its `.SRCINFO`
version and the release one both need a refresh:

```bash
# 1. release package — in packaging/aur/
updpkgsums                              # re-pin sha256 for the new tag tarball
#    (bump pkgver/pkgrel first if the tag changed)
makepkg --printsrcinfo > .SRCINFO

# 2. git package — in packaging/aur-git/  (regenerate so the AUR shows the new version)
makepkg --printsrcinfo > .SRCINFO

# 3. copy PKGBUILD + .SRCINFO of each into its AUR clone and push
#    (clones live at ~/aur/lyrics-tool and ~/aur/lyrics-tool-git)
cp packaging/aur/{PKGBUILD,.SRCINFO}     ~/aur/lyrics-tool/     && \
  git -C ~/aur/lyrics-tool     commit -am "lyrics-tool <new-ver>" && git -C ~/aur/lyrics-tool     push
cp packaging/aur-git/{PKGBUILD,.SRCINFO} ~/aur/lyrics-tool-git/ && \
  git -C ~/aur/lyrics-tool-git commit -am "lyrics-tool-git <new-ver>" && git -C ~/aur/lyrics-tool-git push
```

- `python-syncedlyrics` may only be available from the AUR; the rest of the
  runtime dependencies are in the official repositories.

## Homebrew notes

The formula now lives in its own tap:
**[hamza-abdelmoumene/homebrew-tap](https://github.com/hamza-abdelmoumene/homebrew-tap)**
(`Formula/lyrics-tool.rb`). On a new release, refresh it:

- Bump `url`/`sha256` to the new PyPI sdist, and re-pin the dependency `resource`
  blocks with `brew update-python-resources Formula/lyrics-tool.rb` (or
  `brew bump-formula-pr`). The tap's `brew test` CI builds it on macOS + Linux.
- `../homebrew/` in this repo is just a pointer — the tap is the source of truth.
