#!/usr/bin/env bash
# afterMerge helper (decision merge-reinstalls-from-main): move the pinned checkout <clone>-live,
# a worktree of the clone on a detached HEAD, to the new local main, then run the install from it,
# so the ~/.claude links point at main and never at the caller's tree. Makes the pinned checkout
# when it is missing. install.sh and install.ps1 make it too, because they also run on their own.
# Windows (MINGW, MSYS, CYGWIN) runs install.ps1; elsewhere install.sh.
# A step that cannot move or install prints one stderr line naming the fix and exits 1.
#
# The move never exposes a mix (owner ruling 2026-10-15, install-set). The new main is checked out
# in a fresh worktree <clone>-live-<commit>, and <clone>-live becomes a link to it by one rename of
# the link. A reader that loads through the ~/.claude links sees the old tree or the new one. The
# old worktree stays until the next move. The first move from a plain <clone>-live directory (as
# install.sh makes it) renames that directory to <clone>-live-<its commit> first; between the two
# renames the path is absent for a moment, and a guard load retries through that.
# Without symlink rights the pinned checkout is switched in place (git switch --detach), which
# writes the files one at a time; a debt names it.
# Every pinned worktree is locked, so the janitor sweep never removes it.
fail() { echo "install not run: $1" >&2; exit 1; }

clone=$(git worktree list --porcelain 2>/dev/null | sed -n '1s/^worktree //p')
[ -n "$clone" ] || fail "no git clone found here; run merge/install_from_main.sh from inside the clone"
pin="$clone-live"
commit=$(git rev-parse --verify -q refs/heads/main) \
  || fail "no branch named main, so $pin cannot move; create it with git branch main origin/main, then run merge/install_from_main.sh"
REASON="claude-settings live pin"

# Canonical path, so C:/x and /c/x compare equal. Prints nothing when DIR is empty or missing.
canon() { [ -n "$1" ] && ( cd "$1" 2>/dev/null && pwd -P ); }
common() { git -C "$1" rev-parse --path-format=absolute --git-common-dir 2>/dev/null; }
# True when DIR is detached at main's commit.
at_main() { ! git -C "$1" symbolic-ref -q HEAD >/dev/null 2>&1 && [ "$(git -C "$1" rev-parse HEAD 2>/dev/null)" = "$commit" ]; }

# Makes $pin a link to worktree $1 by one rename of the link. Returns 1 when no real link can be made.
point_at() {
  export MSYS=winsymlinks:nativestrict
  rm -f "$pin.tmp"
  { ln -s "$1" "$pin.tmp" 2>/dev/null && [ -L "$pin.tmp" ]; } || { rm -f "$pin.tmp"; return 1; }
  if [ -L "$pin" ]; then
    mv -fT "$pin.tmp" "$pin" 2>/dev/null || mv -fh "$pin.tmp" "$pin" || { rm -f "$pin.tmp"; return 1; }
  else
    mv "$pin.tmp" "$pin" || { rm -f "$pin.tmp"; return 1; }
  fi
}

# Removes the <clone>-live-<12 hex> worktrees except $1 (the new one) and $2 (the one before it).
# One that cannot be removed stays; the next move tries again.
prune_trees() {
  git worktree list --porcelain | sed -n 's/^worktree //p' | while IFS= read -r w; do
    s="${w##*-}"
    case "$w" in "$pin"-*) ;; *) continue ;; esac
    [ "${#s}" = 12 ] && [ -z "${s//[0-9a-f]/}" ] || continue
    [ "$(canon "$w")" = "$(canon "$1")" ] && continue
    [ -n "$2" ] && [ "$(canon "$w")" = "$(canon "$2")" ] && continue
    git worktree remove -f -f "$w" >/dev/null 2>&1
  done
}

# Moves the pinned checkout to main's commit.
move_pin() {
  short=$(git rev-parse --short=12 "$commit")
  tree="$pin-$short"
  prev=""; [ -e "$pin" ] && prev=$(canon "$pin")
  if [ -d "$tree" ] && at_main "$tree"; then :   # a tree from an earlier move is already at main
  else
    [ ! -e "$tree" ] || fail "$tree is in the way; move it aside, then run merge/install_from_main.sh"
    err=$(git worktree add -q --detach --lock --reason "$REASON" "$tree" "$commit" 2>&1) \
      || fail "cannot make the pinned checkout $tree: $err; fix that, then run merge/install_from_main.sh"
  fi
  if [ ! -L "$pin" ]; then
    # A plain directory (made by install.sh): rename it to <clone>-live-<its commit>, retrying while a reader holds a file.
    old=$(git -C "$pin" rev-parse --short=12 HEAD 2>/dev/null)
    if [ -n "$old" ] && [ ! -e "$pin-$old" ]; then
      git worktree unlock "$pin" >/dev/null 2>&1
      i=0
      until git worktree move "$pin" "$pin-$old" >/dev/null 2>&1; do
        i=$((i + 1)); [ "$i" -lt 30 ] || break
        sleep 0.2
      done
      if [ -d "$pin-$old" ]; then
        git worktree lock --reason "$REASON" "$pin-$old" >/dev/null 2>&1
        prev=$(canon "$pin-$old")
      fi
    fi
  fi
  if [ -e "$pin" ] && [ ! -L "$pin" ]; then
    # Could not rename it, or no link can be made: switch it in place.
    err=$(git -C "$pin" switch -q --detach "$commit" 2>&1) \
      || fail "cannot move the pinned checkout $pin to main: $err; fix that (git -C \"$pin\" status), then run merge/install_from_main.sh"
  elif ! point_at "$tree"; then
    [ -e "$pin" ] || fail "cannot link $pin to $tree; make $pin by hand (git worktree add --detach $pin main), then run merge/install_from_main.sh"
    err=$(git -C "$pin" switch -q --detach "$commit" 2>&1) \
      || fail "cannot move the pinned checkout $pin to main: $err; fix that (git -C \"$pin\" status), then run merge/install_from_main.sh"
  else
    prune_trees "$tree" "$prev"
  fi
}

if [ -L "$pin" ] && [ ! -e "$pin" ]; then rm -f "$pin"; fi   # a link whose tree is gone
if [ ! -e "$pin" ]; then
  err=$(git worktree add -q --detach --lock --reason "$REASON" "$pin" "$commit" 2>&1) \
    || fail "cannot make the pinned checkout $pin: $err; fix that, then run merge/install_from_main.sh"
else
  a=$(canon "$(common "$pin")"); b=$(canon "$(common "$clone")")
  { [ -n "$a" ] && [ "$a" = "$b" ]; } \
    || fail "$pin is not a worktree of this clone; move it aside, then run merge/install_from_main.sh"
  at_main "$pin" || move_pin
  git worktree lock --reason "$REASON" "$pin" >/dev/null 2>&1   # lock an unlocked pin; fails harmlessly when locked
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
