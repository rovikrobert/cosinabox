#!/bin/bash
set -e
PWD_ABS=$(pwd -P)
if [[ "$PWD_ABS" != "$HOME/.worktrees/cosinabox/"* ]]; then
  echo "::warning::Not in a cosinabox worktree. Current path: $PWD_ABS"
  echo "::warning::Run: git worktree add ~/.worktrees/cosinabox/<branch> -b <branch>"
fi
exit 0
