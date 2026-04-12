#!/bin/bash
set -e
HOOK_DIR=$(git rev-parse --git-path hooks)
SOURCE=".cosinabox/pre-commit"
TARGET="$HOOK_DIR/pre-commit"
if [ ! -f "$SOURCE" ]; then
  echo "::error::$SOURCE not found. Run from your user repo root."
  exit 1
fi
ln -sf "$(pwd)/$SOURCE" "$TARGET"
chmod +x "$SOURCE"
echo "::notice::Installed cosinabox pre-commit hook at $TARGET"
