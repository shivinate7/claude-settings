#!/usr/bin/env bash
# afterMerge helper (decision merge-reinstalls-from-main): move the pinned checkout <clone>-live,
# a worktree of the clone on a detached HEAD, to the new local main, then run the install from it,
# so the ~/.claude links point at main and never at the caller's tree. Makes the pinned checkout
# when it is missing. install.sh and install.ps1 make it too, because they also run on their own.
# Windows (MINGW, MSYS, CYGWIN) runs install.ps1; elsewhere install.sh.
# A step that cannot move or install prints one stderr line naming the fix and exits 1.
fail() { echo "install not run: $1" >&2; exit 1; }

clone=$(git worktree list --porcelain 2>/dev/null | sed -n '1s/^worktree //p')
[ -n "$clone" ] || fail "no git clone found here; run merge/install_from_main.sh from inside the clone"
pin="$clone-live"
commit=$(git rev-parse --verify -q refs/heads/main) \
  || fail "no branch named main, so $pin cannot move; create it with git branch main origin/main, then run merge/install_from_main.sh"

# Canonical path, so C:/x and /c/x compare equal. Prints nothing when DIR is empty or missing.
canon() { [ -n "$1" ] && ( cd "$1" 2>/dev/null && pwd -P ); }
common() { git -C "$1" rev-parse --path-format=absolute --git-common-dir 2>/dev/null; }
if [ ! -e "$pin" ]; then
  git worktree add -q --detach "$pin" "$commit" 2>/dev/null \
    || fail "cannot make the pinned checkout $pin; free that path, then run merge/install_from_main.sh"
else
  a=$(canon "$(common "$pin")"); b=$(canon "$(common "$clone")")
  { [ -n "$a" ] && [ "$a" = "$b" ]; } \
    || fail "$pin is not a worktree of this clone; move it aside, then run merge/install_from_main.sh"
  git -C "$pin" switch -q --detach "$commit" 2>/dev/null \
    || fail "cannot move the pinned checkout $pin to main; clean it up (git -C \"$pin\" status), then run merge/install_from_main.sh"
fi

case "$(uname)" in
  MINGW*|MSYS*|CYGWIN*)
    [ -f "$pin/install.ps1" ] || fail "$pin has no install.ps1"
    echo "Installing from $pin"
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$pin/install.ps1")" ;;
  *)
    [ -f "$pin/install.sh" ] || fail "$pin has no install.sh"
    echo "Installing from $pin"
    bash "$pin/install.sh" ;;
esac
