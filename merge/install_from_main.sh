#!/usr/bin/env bash
# afterMerge helper (decision merge-reinstalls-from-main): move the pinned checkout <clone>-live,
# a worktree of the clone on a detached HEAD, to the new local main, then run the install from it,
# so the ~/.claude links point at main and never at the caller's tree. Makes the pinned checkout
# when it is missing. install.sh and install.ps1 make it too, because they also run on their own.
# Windows (MINGW, MSYS, CYGWIN) runs install.ps1; elsewhere install.sh.
# A step that cannot move or install prints one stderr line naming the fix and exits 1.
#
# The move never exposes a mix (merge-reinstalls-from-main). The new main is checked out
# in a fresh worktree <clone>-live-<commit>, and <clone>-live becomes a link to it by one rename of
# the link. A reader that loads through the ~/.claude links sees the old tree or the new one. The
# old worktree stays until the next move. The first move from a plain <clone>-live directory (as
# install.sh makes it) renames that directory to <clone>-live-<its commit> first; between the two
# renames the path is absent for a moment, and a guard load retries through that.
# Without symlink rights the pinned checkout is switched in place (git switch --detach), which
# writes the files one at a time (a live reader can see a mix there).
# A settings.json that only reordered keys is restored from HEAD first and does not count as a change.
# A pin with tracked changes is never moved, switched or removed, nor is an old tree with them: the
# run prints one stderr line naming the pin and exits 1; the SessionStart hook writes that line to
# the install log. A <clone>-live-<commit> tree whose only changes are missing tracked files (a git
# worktree add killed part way) has them restored before it is reused.
# The run tests for link rights before it moves anything, so a host without them never loses the
# pin path.
# The run takes the install lock the installers take (install-hooks-whole): one
# install at a time. It reads main's commit only once it holds the lock, so a run that waited never
# moves the pin back to an older main. It holds the lock through the installer, and hands the
# installer its id as CLAUDE_SETTINGS_LOCK_TOKEN; the lock file holds that id, so the installer
# runs under this lock and does not wait on it. The run logs a start line once it holds the lock
# and an end line with its real exit code when it ends, each with a unique id and its pid, in the
# install log install.sh writes. The installer logs its own pair inside this one.
# ponytail: this lock code copies install.sh's, because install.sh runs on load and cannot be
# sourced; one shared lock file is the one home. A shared lock script is the upgrade.
# Every pinned worktree is locked, so the janitor sweep never removes it.
fail() { echo "install not run: $1" >&2; exit 1; }

clone=$(git worktree list --porcelain 2>/dev/null | sed -n '1s/^worktree //p')
[ -n "$clone" ] || fail "no git clone found here; run merge/install_from_main.sh from inside the clone"
pin="$clone-live"
no_main="no branch named main, so $pin cannot move; create it with git branch main origin/main, then run merge/install_from_main.sh"
git rev-parse --verify -q refs/heads/main >/dev/null || fail "$no_main"   # fail fast, before any lock wait
REASON="claude-settings live pin"

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
INSTALL_LOG="$CLAUDE_DIR/claude-settings-install.log"
INSTALL_LOCK="$CLAUDE_DIR/.claude-settings-install.lock"
INSTALL_ID="$(date +%Y%m%d%H%M%S)$$"
# log_stamp: ISO 8601 time with the UTC offset (date +%z gives +HHMM; the colon is added). install.sh has its
# own copy: the two scripts share no sourced file.
log_stamp() { stamp_t=$(date +%Y-%m-%dT%H:%M:%S%z); printf '%s:%s' "${stamp_t%??}" "${stamp_t#"${stamp_t%??}"}"; }
log_line() { printf '%s install_from_main.sh: %s id=%s pid=%s\n' "$(log_stamp)" "$1" "$INSTALL_ID" "$$" >> "$INSTALL_LOG"; }
release_lock() {   # the EXIT trap: the end line with the run's real exit, then the lock if it is still this run's
  rc=$?
  trap - EXIT
  log_line "end exit=$rc"
  [ "$(head -n 1 "$INSTALL_LOCK" 2>/dev/null)" = "$INSTALL_ID" ] && rm -f "$INSTALL_LOCK"
  return "$rc"
}
take_lock() {
  mkdir -p "$CLAUDE_DIR"
  tries=$(( ${CLAUDE_SETTINGS_LOCK_WAIT:-60} * 5 ))
  while ! ( set -C; printf '%s\n' "$INSTALL_ID" > "$INSTALL_LOCK" ) 2>/dev/null; do
    if [ -n "$(find "$INSTALL_LOCK" -mmin +10 2>/dev/null)" ]; then rm -f "$INSTALL_LOCK"; continue; fi
    tries=$((tries - 1))
    [ "$tries" -gt 0 ] || fail "another install holds the lock $INSTALL_LOCK; nothing was moved. Run merge/install_from_main.sh again when it ends, or delete that file if no install is running."
    sleep 0.2
  done
  trap 'release_lock' EXIT
  log_line start
}

# Canonical path, so C:/x and /c/x compare equal. Prints nothing when DIR is empty or missing.
canon() { [ -n "$1" ] && ( cd "$1" 2>/dev/null && pwd -P ); }
common() { git -C "$1" rev-parse --path-format=absolute --git-common-dir 2>/dev/null; }
# True when DIR is detached at main's commit.
at_commit() { ! git -C "$1" symbolic-ref -q HEAD >/dev/null 2>&1 && [ "$(git -C "$1" rev-parse HEAD 2>/dev/null)" = "$commit" ]; }
# A tracked file missing is the mark of a git worktree add killed part way: the tree lacks files,
# it holds no one's edits. not_deletions prints DIR's other tracked changes.
missing_files() { git -C "$1" status --porcelain --untracked-files=no 2>/dev/null | grep -qE '^(D.|.D)'; }
not_deletions() { git -C "$1" status --porcelain --untracked-files=no 2>/dev/null | grep -vE '^(D.|.D)'; }
# True when DIR is detached at main's commit with no tracked file missing.
at_main() { at_commit "$1" && ! missing_files "$1"; }

# Frees DIR of a settings.json save that only reordered keys (the app and CLI rewrite the linked file).
# Only when settings.json is DIR's one tracked change and parses to the same JSON as HEAD's: it is then
# restored from HEAD. Any other change, an unparsable file or no python3 leaves DIR as it is (fail safe).
restore_reordered_settings() {
  [ "$(git -C "$1" status --porcelain --untracked-files=no 2>/dev/null)" = " M settings.json" ] || return 0
  command -v python3 >/dev/null 2>&1 || return 0
  git -C "$1" show HEAD:settings.json 2>/dev/null | python3 -c '
import json, sys
sys.exit(0 if json.load(sys.stdin) == json.load(open(sys.argv[1])) else 1)' "$1/settings.json" 2>/dev/null \
    && git -C "$1" checkout -q -- settings.json >/dev/null 2>&1
  return 0
}

# Makes $pin a link to worktree $1 by one rename of the link. Returns 1 when no real link can be made.
# The temp name is per run, so a run that died never leaves a name another run shares.
point_at() {
  export MSYS=winsymlinks:nativestrict
  tmp="$pin.tmp.$$"
  rm -f "$tmp"
  { ln -s "$1" "$tmp" 2>/dev/null && [ -L "$tmp" ]; } || { rm -f "$tmp"; return 1; }
  if [ -L "$pin" ]; then
    mv -fT "$tmp" "$pin" 2>/dev/null || mv -fh "$tmp" "$pin" || { rm -f "$tmp"; return 1; }
  else
    mv "$tmp" "$pin" || { rm -f "$tmp"; return 1; }
  fi
}

# True when this host can make a real link. Tested before any move, so a refusal moves nothing.
can_link() {
  export MSYS=winsymlinks:nativestrict
  probe="$pin.probe.$$"
  rm -f "$probe"
  ln -s "$clone" "$probe" 2>/dev/null && [ -L "$probe" ]; r=$?
  rm -f "$probe"
  return $r
}

# Switches the pinned checkout $pin to main's commit in place.
switch_in_place() {
  err=$(git -C "$pin" switch -q --detach "$commit" 2>&1) \
    || fail "cannot move the pinned checkout $pin to main: $err; fix that (git -C \"$pin\" status), then run merge/install_from_main.sh"
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
    restore_reordered_settings "$w"
    [ -z "$(git -C "$w" status --porcelain --untracked-files=no 2>/dev/null)" ] || continue   # never drop a tree with tracked changes
    git worktree remove -f -f "$w" >/dev/null 2>&1
  done
}

# Moves the pinned checkout to main's commit.
move_pin() {
  restore_reordered_settings "$pin"
  if [ -n "$(git -C "$pin" status --porcelain --untracked-files=no 2>/dev/null)" ]; then
    # Tracked changes in the pin are someone's work: move, switch and remove nothing.
    fail "the pinned checkout $pin has tracked changes, so it was not moved; commit or discard them there (git -C \"$pin\" status), then run merge/install_from_main.sh"
  fi
  if ! can_link; then switch_in_place; return; fi   # no link rights: leave the pin path as it is
  short=$(git rev-parse --short=12 "$commit")
  tree="$pin-$short"
  prev=""; [ -e "$pin" ] && prev=$(canon "$pin")
  # A tree at main's commit whose only changes are missing files: restore them from that commit.
  if [ -d "$tree" ] && at_commit "$tree" && missing_files "$tree" && [ -z "$(not_deletions "$tree")" ]; then
    git -C "$tree" checkout -q HEAD -- . >/dev/null 2>&1
  fi
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
    switch_in_place   # could not rename it
  elif ! point_at "$tree"; then
    [ -e "$pin" ] || fail "cannot link $pin to $tree; make $pin by hand (git worktree add --detach $pin main), then run merge/install_from_main.sh"
    switch_in_place
  else
    prune_trees "$tree" "$prev"
  fi
}

take_lock
commit=$(git rev-parse --verify -q refs/heads/main) || fail "$no_main"   # read under the lock
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

# The installer runs under this run's lock; the EXIT trap logs the end line with its exit code.
case "$(uname)" in
  MINGW*|MSYS*|CYGWIN*)
    [ -f "$pin/install.ps1" ] || fail "$pin has no install.ps1"
    echo "Installing from $pin"
    CLAUDE_SETTINGS_LOCK_TOKEN="$INSTALL_ID" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$pin/install.ps1")" ;;
  *)
    [ -f "$pin/install.sh" ] || fail "$pin has no install.sh"
    echo "Installing from $pin"
    CLAUDE_SETTINGS_LOCK_TOKEN="$INSTALL_ID" bash "$pin/install.sh" ;;
esac
