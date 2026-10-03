#!/usr/bin/env bash
# Install the main-ref hook into the current repo: sh githooks/main-ref/install.sh
# Copies into core.hooksPath when the repo sets one, else into the common .git hooks dir.
# The common dir is shared by every worktree of the clone. Never edits core.hooksPath.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
dir="$(git config --get core.hooksPath || true)"
[ -n "$dir" ] || dir="$(git rev-parse --git-common-dir)/hooks"
mkdir -p "$dir"
cp "$here/reference-transaction" "$dir/reference-transaction"
chmod +x "$dir/reference-transaction"
echo "installed $dir/reference-transaction"
