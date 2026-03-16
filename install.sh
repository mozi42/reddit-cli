#!/usr/bin/env bash
set -euo pipefail

# Minimal installer: symlink into ~/.local/bin
# Note: ensure ~/.local/bin is on PATH (may require a new shell / harness restart).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
TARGET="$SCRIPT_DIR/reddit_cli.py"

if [[ ! -f "$TARGET" ]]; then
  echo "Expected $TARGET" >&2
  exit 1
fi

chmod +x "$TARGET"
mkdir -p "$HOME/.local/bin"
ln -sf "$TARGET" "$HOME/.local/bin/reddit-cli"

echo "Installed: $HOME/.local/bin/reddit-cli -> $TARGET"
if command -v reddit-cli >/dev/null 2>&1; then
  echo "On PATH: $(command -v reddit-cli)"
else
  echo "Note: ~/.local/bin not currently on PATH. Restart your shell/harness." 
fi
