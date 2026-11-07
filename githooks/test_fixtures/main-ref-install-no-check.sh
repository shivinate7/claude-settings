#!/bin/sh
# Install the main-ref hook into the current repo: sh githooks/main-ref/install.sh
# Copies into core.hooksPath when the repo sets one, else into the common .git hooks dir.
# The common dir is shared by every worktree of the clone. Never edits core.hooksPath.
# Git expands a leading ~ in core.hooksPath and resolves a relative one against the root of the
# worktree the hook runs in, so a relative path gets one copy per worktree that exists now.
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
# Each command substitution is its own assignment: as an argument, its failure escapes set -e.
cdir="$(git rev-parse --git-common-dir)"
dir="$(git config --path --get core.hooksPath)" || dir=""
put() {
  mkdir -p "$1" || { echo "ERROR: cannot create $1; in a linked worktree .git is a file" >&2; exit 1; }
  cp "$here/reference-transaction" "$1/reference-transaction"
  chmod +x "$1/reference-transaction"
  echo "installed $1/reference-transaction"
}
case "$dir" in
  "") put "$cdir/hooks" ;;
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
