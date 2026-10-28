#!/bin/sh
# Install the main-ref hook into the current repo: sh githooks/main-ref/install.sh
# Copies into core.hooksPath when the repo sets one, else into the common .git hooks dir.
# The common dir is shared by every worktree of the clone. Never edits core.hooksPath.
# Git expands a leading ~ in core.hooksPath and resolves a relative one against the root of the
# worktree the hook runs in, so a relative path gets one copy per worktree that exists now.
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
dir="$(git config --path --get core.hooksPath || true)"
put() {
  mkdir -p "$1"
  cp "$here/reference-transaction" "$1/reference-transaction"
  chmod +x "$1/reference-transaction"
  echo "installed $1/reference-transaction"
}
case "$dir" in
  "") put "$(git rev-parse --git-common-dir)/hooks" ;;
  /*) put "$dir" ;;
  *)
    # The first entry of a bare repo is its git dir, which is where git resolves the path there.
    wts="$(git worktree list --porcelain)"
    printf '%s\n' "$wts" | sed -n 's/^worktree //p' | while IFS= read -r wt; do
      if [ -d "$wt" ]; then put "$wt/$dir"; else echo "WARNING: worktree $wt is missing; not installed there" >&2; fi
    done
    echo "WARNING: core.hooksPath '$dir' is relative. A worktree added later has no guard until you rerun this installer." >&2
    ;;
esac
