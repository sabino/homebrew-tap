# sabino's Homebrew tap

[![CI](https://github.com/sabino/homebrew-tap/actions/workflows/ci.yml/badge.svg)](https://github.com/sabino/homebrew-tap/actions/workflows/ci.yml)
[![Cask updates](https://github.com/sabino/homebrew-tap/actions/workflows/update-audifern.yml/badge.svg)](https://github.com/sabino/homebrew-tap/actions/workflows/update-audifern.yml)

Versioned, checksum-pinned macOS applications by [sabino](https://github.com/sabino).
This tap works with Homebrew and [Malt (`mt`)](https://github.com/indaco/malt).

## Install Audifern

[Audifern](https://github.com/sabino/audifern) provides native, local Bluetooth
controls for compatible hearing aids. The cask installs the official universal
DMG for **macOS 14 or later**, on Apple Silicon and Intel. Releases are Developer
ID signed and Apple-notarized.

Using Homebrew:

```sh
brew install --cask sabino/tap/audifern
```

Using Malt:

```sh
mt install --cask sabino/tap/audifern
```

The qualified name is `owner/tap/app`: `sabino/tap/audifern`. The GitHub repository
is named `homebrew-tap`; package managers omit its `homebrew-` prefix. An explicit
`tap` command is unnecessary for the qualified install.

`sabino/audifern` is not a portable install shorthand: it omits the tap component.
Use the three-part name above. With Homebrew, you can also tap once and use a bare
app name:

```sh
brew tap sabino/tap
brew install --cask audifern
```

Malt 0.25.2 requires the qualified name for an initial custom-cask install.
Both `mt install --cask sabino/audifern` and `mt install --cask audifern` report
`CaskNotFound`, even after `mt tap sabino/tap`. The full three-part command above
has been tested with a real installation.

## Upgrade or uninstall

Quit Audifern before upgrading its installed application bundle.

```sh
brew update
brew upgrade --cask audifern
brew uninstall --cask audifern
```

Malt pins each tap to a commit. Refresh the tap before checking for an update:

```sh
mt tap --refresh sabino/tap
mt upgrade --cask audifern
mt uninstall --cask audifern
```

The cask has no `zap` or custom uninstall hooks. Removing the application
preserves your audiograms, presets, preferences and other app data.
App usage, compatibility and pairing are documented in the
[Audifern README](https://github.com/sabino/audifern#readme).

## How updates work

An hourly workflow checks Audifern's latest stable release metadata. If the
pinned version is current, it stops without starting a macOS runner or
downloading the app. GitHub can delay scheduled runs; maintainers can also run
**Actions → Update Audifern → Run workflow**.

When a new release appears, a read-only Mac job checks:

- The exact official asset names, versioned URLs, sizes, GitHub digests and
  `SHA256SUMS`.
- The manifest's source commit, universal architectures and notarization claims.
- The annotated release tag's GPG signature against Audifern's approved public
  maintainer key, and that its commit belongs to upstream `main`.
- The actual DMG and app: Developer ID team, host/widget signatures, hardened
  runtime, secure timestamps, universal executables, stapled Apple tickets and
  Gatekeeper acceptance.
- Homebrew's cask style/audit and a real installation of the exact candidate.
  The app is never launched by these checks.

Only after these checks pass does a separate job propose a cask-only pull
request. GitHub signs the automated commit. The workflow explicitly dispatches
CI because pull requests created with `GITHUB_TOKEN` do not automatically trigger
another workflow. Required **Tap checks** and **Install Audifern** checks gate
automatic merge. Downgrades, changed digests for an existing version and races
with newer changes stop the update for review.

This repository contains no Apple certificate, notarization secret, personal
GPG private key or cross-repository access token. The release key in `.github/`
is **public** and is used only to verify Audifern's maintainer signature.
Maintainer commits use sabino's signing key; automated commits use GitHub's
verified bot signature.

## Local checks

```sh
python3 -m unittest discover -s Tests -v
ruby -c Casks/audifern.rb
bash -n scripts/check-install.sh
```

On a Mac with GitHub CLI and GnuPG available, independently verify the pinned
release without installing or launching it:

```sh
python3 scripts/update_audifern.py --check
```

Network access to GitHub and Apple's ticket service is required. Public GitHub
API queries use your existing `gh` authentication, or `GH_TOKEN` in Actions.

GPL-3.0-only. See [LICENSE](LICENSE). Audifern's own source and license are
available in its [repository](https://github.com/sabino/audifern).
