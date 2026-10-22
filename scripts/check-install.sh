#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail

tap_root=$(cd "$(dirname "$0")/.." && pwd)
: "${RUNNER_TEMP:?This check runs in an isolated GitHub macOS runner.}"

# The generated candidate can be uncommitted. Copy that exact recipe into
# Homebrew's local tap clone rather than inadvertently testing the old HEAD.
brew tap sabino/tap "$tap_root"
if brew commands --quiet | rg -qx trust; then
  brew trust --tap sabino/tap
fi
cp "$tap_root/Casks/audifern.rb" "$(brew --repository sabino/tap)/Casks/audifern.rb"
brew style --cask sabino/tap/audifern
brew audit --cask --strict sabino/tap/audifern
mkdir -p "$RUNNER_TEMP/audifern-applications"
brew install --cask --appdir="$RUNNER_TEMP/audifern-applications" sabino/tap/audifern
python3 - "$tap_root" "$RUNNER_TEMP/audifern-applications/Audifern.app" <<'PY'
from pathlib import Path
import sys
sys.path.insert(0, str(Path(sys.argv[1]) / 'scripts'))
from update_audifern import current_cask, verify_app
version, _ = current_cask((Path(sys.argv[1]) / 'Casks/audifern.rb').read_text())
verify_app(Path(sys.argv[2]), version)
print('Homebrew installed the verified universal app; it was not launched.')
PY
