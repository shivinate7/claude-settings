#!/bin/sh
# Install the main-ref hook into the current repo: sh githooks/main-ref/install.sh
# Check the armed copies against main, writing nothing: sh githooks/main-ref/install.sh --check
# Copies into core.hooksPath when the repo sets one, else into the common .git hooks dir.
# The common dir is shared by every worktree of the clone. Never edits core.hooksPath.
# Git expands a leading ~ in core.hooksPath and resolves a relative one against the root of the
# worktree the hook runs in, so a relative path gets one copy per worktree that exists now.
#
# --check compares each armed copy to the main blob of this file's sibling, never to the working
# tree: a branch that edits the hook must not be told to arm its unmerged edit for every worktree.
# The base is local main, else origin/main, else unknown. The branch edit is the HEAD blob: only a
# committed edit counts, so an uncommitted one excuses no stale copy.
# main-ref-check: 1   (the pre-commit hook runs --check only on an installer that carries this marker)
# Exit 0: current, or this branch edits the hook (a NOTE, no remedy). Exit 1: a copy is missing or
# behind main (stderr names the remedy). Exit 2: a read failed (stderr says "unknown").
# Cost: the shared pre-commit hook runs it once per commit: one sh, 5 git reads plus one per armed copy (one more for a relative hooksPath), no files written.
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
mode=install
case "${1:-}" in
  "") ;;
  --check) mode=check ;;
  *) echo "usage: sh githooks/main-ref/install.sh [--check]" >&2; exit 1 ;;
esac
# Each command substitution is its own assignment: as an argument, its failure escapes set -e.
# A failed read in check mode is unknown (exit 2), never a stale copy (exit 1).
unknown() { echo "main-ref check: unknown: $1" >&2; exit 2; }
if [ "$mode" = check ]; then
  cdir="$(git rev-parse --git-common-dir)" || unknown "cannot read the git dir"
else
  cdir="$(git rev-parse --git-common-dir)"
fi
# git config exits 1 when the key is unset; any other failure means the setting could not be read.
dir="$(git config --path --get core.hooksPath)" && rc=0 || rc=$?
if [ "$rc" -eq 1 ]; then dir=""; elif [ "$rc" -ne 0 ]; then
  if [ "$mode" = check ]; then unknown "cannot read core.hooksPath (git config exited $rc)"; fi
  echo "ERROR: cannot read core.hooksPath (git config exited $rc)" >&2; exit 1
fi
# Prints each hooks dir that holds an armed copy, one per line. The one home of the placement rule.
targets() {
  case "$dir" in
    "") printf '%s\n' "$cdir/hooks" ;;
    /*|[A-Za-z]:/*|[A-Za-z]:\\*) printf '%s\n' "$dir" ;;
    *)
      # The first entry of a bare repo is its git dir, which is where git resolves the path there.
      wts="$(git worktree list --porcelain)" || return 1
      printf '%s\n' "$wts" | sed -n 's/^worktree //p' | while IFS= read -r wt; do
        if [ -d "$wt" ]; then printf '%s\n' "$wt/$dir"; else echo "WARNING: worktree $wt is missing; not installed there" >&2; fi
      done
      ;;
  esac
}
if [ "$mode" = check ]; then
  main_blob="$(git -C "$here" rev-parse --verify --quiet main:githooks/main-ref/reference-transaction)" || main_blob=""
  if [ -z "$main_blob" ]; then
    main_blob="$(git -C "$here" rev-parse --verify --quiet origin/main:githooks/main-ref/reference-transaction)" || main_blob=""
  fi
  [ -n "$main_blob" ] || unknown "no main or origin/main holds githooks/main-ref/reference-transaction to compare against"
  src_blob="$(git -C "$here" rev-parse --verify --quiet HEAD:githooks/main-ref/reference-transaction)" || src_blob=""
  [ -n "$src_blob" ] || unknown "HEAD holds no githooks/main-ref/reference-transaction"
  list="$(targets)" || unknown "cannot list the worktrees"
  stale=""; behind=""; unread=""
  while IFS= read -r d; do
    [ -n "$d" ] || continue
    f="$d/reference-transaction"
    if [ ! -e "$f" ] && [ ! -L "$f" ]; then
      # Missing counts as stale only when the nearest existing ancestor is a searchable directory;
      # a file or an unreadable directory on the way is a stat error, which is unknown.
      p="$d"
      while [ ! -e "$p" ] && [ "$p" != / ] && [ "$p" != . ]; do p="$(dirname "$p")"; done
      if [ -d "$p" ] && [ -x "$p" ]; then stale="$stale $f"; else unread="$unread $f"; fi
      continue
    fi
    if [ ! -f "$f" ]; then unread="$unread $f"; continue; fi
    blob="$(git hash-object "$f")" || blob=""
    if [ -z "$blob" ]; then unread="$unread $f"; elif [ "$blob" != "$main_blob" ]; then behind="$behind $f"; fi
  done <<EOT
$list
EOT
  if [ -n "$unread" ]; then echo "main-ref check: unknown: cannot read the armed copy:$unread" >&2; fi
  if [ "$src_blob" = "$main_blob" ]; then
    if [ -n "$stale$behind" ]; then
      echo "main-ref check: the armed reference-transaction is missing or behind main:$stale$behind" >&2
      echo "  Remedy: sh githooks/main-ref/install.sh" >&2
      exit 1
    fi
  else
    if [ -n "$stale" ]; then
      echo "main-ref check: no armed reference-transaction at:$stale" >&2
      echo "  Remedy: run githooks/main-ref/install.sh from a checkout whose copy matches main; this branch edits the hook." >&2
      exit 1
    fi
    if [ -n "$behind" ]; then
      echo "NOTE: the armed copy at$behind is not main's. This branch edits the hook, so the check allows it; land the edit, then re-arm from main." >&2
    fi
  fi
  [ -z "$unread" ] || exit 2
  exit 0
fi
put() {
  mkdir -p "$1" || { echo "ERROR: cannot create $1; in a linked worktree .git is a file" >&2; exit 1; }
  cp "$here/reference-transaction" "$1/reference-transaction"
  chmod +x "$1/reference-transaction"
  echo "installed $1/reference-transaction"
}
list="$(targets)"
while IFS= read -r d; do
  [ -n "$d" ] || continue
  put "$d"
done <<EOT
$list
EOT
case "$dir" in
  ""|/*|[A-Za-z]:/*|[A-Za-z]:\\*) ;;
  *) echo "WARNING: core.hooksPath '$dir' is relative. A worktree added later has no guard until you rerun this installer." >&2 ;;
esac
