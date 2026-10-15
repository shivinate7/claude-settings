#!/usr/bin/env bash
# afterMerge helper (record merge-reinstalls-from-main, "The ruling"): move the pinned checkout
# <clone>-live to the new local main, then run the install from it. The links in ~/.claude point
# at that checkout, so a branch switch in the clone or in the caller's tree changes no live
# setting. It never installs from the caller's tree or the clone: either may sit on a lane branch.
# Windows runs install.ps1, every other host runs install.sh. When the pinned checkout cannot
# move or the install cannot start, it prints one stderr line naming the fix and exits non-zero.
# Limit: the pinned-checkout code here repeats install.sh's. install.sh runs from the pinned
# checkout, and this script runs from the caller's tree, so neither can source the other.
fail() { echo "install not run: $1" >&2; exit 1; }

clone=$(git worktree list --porcelain 2>/dev/null | sed -n '1s/^worktree //p')
[ -n "$clone" ] || fail "no git clone found here; run the merge from inside the clone"
pin="$clone-live"
want=$(git -C "$clone" rev-parse -q --verify refs/heads/main 2>/dev/null) \
  || fail "no branch named main, so $pin cannot move; create branch main in $clone and run again"

if [ ! -e "$pin" ] && [ ! -L "$pin" ]; then
  git -C "$clone" worktree prune
  err=$(git -C "$clone" worktree add -q --detach "$pin" "$want" 2>&1) \
    || fail "could not make $pin: $(printf '%s' "$err" | tr '\n' ' ')"
else
  # Only a linked worktree of this clone may be moved. Any other thing at the path stays as it is.
  gd=$(git -C "$pin" rev-parse --absolute-git-dir 2>/dev/null)
  case "$gd" in
    "$(git -C "$clone" rev-parse --absolute-git-dir)"/worktrees/*) [ -f "$pin/.git" ] || gd="" ;;
    *) gd="" ;;
  esac
  [ -n "$gd" ] || fail "$pin exists and is not a worktree of $clone; move it away and run again"
  err=$(git -C "$pin" switch -q --detach "$want" 2>&1) \
    || fail "could not move $pin to main: $(printf '%s' "$err" | tr '\n' ' ')"
fi

echo "Installing from $pin"
case "$(uname)" in
  MINGW*|MSYS*|CYGWIN*)
    command -v powershell.exe >/dev/null 2>&1 || fail "powershell.exe not found on PATH; run $pin/install.ps1 by hand"
    ps=$(cygpath -w "$pin/install.ps1" 2>/dev/null || printf '%s' "$pin/install.ps1")
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$ps" ;;
  *) bash "$pin/install.sh" ;;
esac
