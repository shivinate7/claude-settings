#!/bin/sh
# Install the roadmap note-cap pre-commit (step c138): sh roadmap/hooks/install.sh
# Copies roadmap/hooks/pre-commit into the hooks dir git uses: core.hooksPath when the repo sets one
# (a relative path is resolved against the worktree root, as git does), else the common .git hooks
# dir shared by every worktree, as main's githooks/main-ref/install.sh does. Never edits
# core.hooksPath and leaves every other hook (main-ref's reference-transaction) in place. A pre-commit
# already there is moved to pre-commit.pre-c138 and run after the cap check. Safe to run again.
set -eu
src="$(cd "$(dirname "$0")" && pwd)/pre-commit"
top="$(git rev-parse --show-toplevel)"
cd "$top"
dir="$(git config --type=path --get core.hooksPath || true)"
if [ -n "$dir" ]; then
  case "$dir" in /*) ;; *) dir="$top/$dir" ;; esac
else
  dir="$(git rev-parse --path-format=absolute --git-common-dir)/hooks"
fi
mkdir -p "$dir"
dir="$(cd "$dir" && pwd -P)"
case "$dir" in
  "$(cd "$(dirname "$src")" && pwd -P)")
    echo "install.sh: core.hooksPath points at roadmap/hooks (the old c138 setup), which turns off the" >&2
    echo "hooks in .git/hooks (main-ref) for every worktree. Run: git config --unset core.hooksPath" >&2
    echo "then run this again, and rerun githooks/main-ref/install.sh from a main checkout." >&2
    exit 1 ;;
esac
marker="roadmap-note-cap pre-commit dispatcher"
if [ -e "$dir/pre-commit" ] && ! grep -q "$marker" "$dir/pre-commit"; then
  if [ -e "$dir/pre-commit.pre-c138" ]; then
    echo "install.sh: both $dir/pre-commit and pre-commit.pre-c138 exist; merge them by hand, then rerun." >&2
    exit 1
  fi
  mv "$dir/pre-commit" "$dir/pre-commit.pre-c138"
  echo "moved the existing pre-commit to $dir/pre-commit.pre-c138; it still runs, after the cap check"
fi
cp "$src" "$dir/pre-commit.tmp.$$"
chmod +x "$dir/pre-commit.tmp.$$"
mv "$dir/pre-commit.tmp.$$" "$dir/pre-commit"
echo "installed $dir/pre-commit"
