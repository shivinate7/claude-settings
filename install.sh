#!/usr/bin/env bash
# Wire ~/.claude to the files in this repo. Linux/macOS local, and Claude Code cloud sessions.
#
#   Local (from a clone):   bash install.sh
#   Cloud setup script:     curl -fsSL https://raw.githubusercontent.com/shivinate7/claude-settings/main/install.sh | bash -s -- --cloud
#
# What it does:
#   ~/.claude/CLAUDE.md      -> one-line pointer: @<repo>/CLAUDE.md
#   ~/.claude/agents/*.md    -> role definitions (builder, reviewer): local symlinks, cloud copies
#   ~/.claude/lint/*         -> STE linter and report guard: local symlinks, cloud copies
#   ~/.claude/hooks/*        -> PreToolUse guard + session-start line: local symlinks, cloud copies
#   ~/.claude/skills/<name>  -> one whole-directory symlink per shipped skill, local; cloud copies
#   ~/.claude/settings.json  -> local: symlink to <repo>/settings.json
#                               cloud: generated copy of settings.json plus a SessionStart hook
#                                      that re-runs this script, so every new cloud session pulls
#                                      the latest files from GitHub.
set -u

# install.ps1 is the Windows installer. Write nothing first.
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) echo "install.sh does not run on Windows. Use install.ps1: powershell -ExecutionPolicy Bypass -File ./install.ps1"; exit 0;; esac

REPO="shivinate7/claude-settings"
REF="${CLAUDE_SETTINGS_REF:-main}"
RAW="https://raw.githubusercontent.com/${REPO}/${REF}"
TARBALL="https://github.com/${REPO}/archive/refs/heads/${REF}.tar.gz"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

CLOUD=0
[ "${1:-}" = "--cloud" ] && CLOUD=1
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] && CLOUD=1

log() { printf 'claude-settings: %s\n' "$*"; }

# Exact match for a git origin URL against $REPO on github.com, not a substring test and
# not host-agnostic. Trims trailing whitespace/newline and a trailing slash, drops a
# trailing ".git", then requires the host to be exactly "github.com" and the remaining
# path to be exactly "$REPO" (not merely to end with it). Matches:
#   https://github.com/shivinate7/claude-settings.git   (and without .git)
#   git@github.com:shivinate7/claude-settings.git       (and without .git)
#   ssh://git@github.com:22/shivinate7/claude-settings.git
# and rejects a different host (gitlab.com), extra leading path segments
# (github.com/mirror/shivinate7/claude-settings), and anything with no recognizable
# host at all (a bare relative path, a file:// URL). Case is not folded: an origin
# spelled "GITHUB.COM" is rejected too, the safe direction for a mismatch.
origin_matches_repo() {
  o=$(printf '%s' "$1" | tr -d '\r\n')
  o=$(printf '%s' "$o" | sed -e 's/[[:space:]]*$//')
  o="${o%/}"
  o="${o%.git}"
  o="${o%/}"

  case "$o" in
    *://*)
      rest="${o#*://}"
      rest="${rest#*@}"
      host="${rest%%/*}"
      host="${host%%:*}"
      path="${rest#*/}"
      ;;
    *@*:*)
      rest="${o#*@}"
      host="${rest%%:*}"
      path="${rest#*:}"
      ;;
    *)
      return 1
      ;;
  esac

  [ "$host" = "github.com" ] || return 1
  [ "$path" = "$REPO" ]
}

# A candidate directory is this repo's checkout only if: it is inside a git worktree,
# that worktree's origin matches $REPO exactly, and it carries the two files install.sh
# always needs. Prints the toplevel and returns 0 on match, prints nothing and returns
# 1 otherwise.
checkout_at() {
  cand="$1"
  [ -n "$cand" ] || return 1
  top=$(git -C "$cand" rev-parse --show-toplevel 2>/dev/null) || return 1
  [ -n "$top" ] || return 1
  origin=$(git -C "$top" remote get-url origin 2>/dev/null) || return 1
  origin_matches_repo "$origin" || return 1
  [ -f "$top/CLAUDE.md" ] || return 1
  [ -f "$top/settings.json" ] || return 1
  printf '%s' "$top"
}

# The directory an existing ~/.claude/CLAUDE.md already points at, if any: parsed the
# same way settings.json's refresh hook and hooks/session_start.sh's divergence check
# read it (the "@<path>/CLAUDE.md" line, "~/" expanded against $HOME). A person's clone
# can sit any number of levels under $HOME (e.g. ~/Developer/claude-settings), which the
# bounded root scan below cannot reach; a pointer already installed by a previous run
# names it exactly, with no assumption about depth. Prints nothing on a missing file, an
# unparseable line, or a path that no longer exists. It is a hint about where to look,
# not a reason to trust what is found there: checkout_at() still applies the same origin
# check to it as to every other candidate.
pointer_dir() {
  md="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md"
  [ -f "$md" ] || return 1
  d=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$md" 2>/dev/null | head -n1)
  # SC2088: the pattern is the literal two characters "~/" that the pointer line holds, never an expansion.
  # shellcheck disable=SC2088
  case "$d" in
    "~"/*) d="$HOME${d#\~}" ;;
  esac
  [ -n "$d" ] && [ -d "$d" ] || return 1
  printf '%s' "$d"
}

# True when DIR is a linked git worktree: --git-dir and --git-common-dir differ only there. Both
# print relative to DIR, so a string compare is enough. A folder with no .git is not one.
is_linked_worktree() {
  gd=$(git -C "$1" rev-parse --git-dir 2>/dev/null) || return 1
  gc=$(git -C "$1" rev-parse --git-common-dir 2>/dev/null) || return 1
  [ "$gd" != "$gc" ]
}

# Locate the source files: the clone this script lives in, else fetch from GitHub.
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/CLAUDE.md" ] && [ -f "$SCRIPT_DIR/settings.json" ]; then
  SRC="$SCRIPT_DIR"
else
  # No file to locate ourselves by (e.g. piped: curl | bash). Look for an existing git
  # checkout of this repo before falling back to fetching a mirror from GitHub: the
  # shell's own cwd is usually this repo already in a cloud session, and using it keeps
  # the checkout's own branch in force instead of overwriting it with a frozen copy of main.
  #
  # A "cwd" from hook JSON on stdin is deliberately NOT read here: in the documented
  # cloud call (`curl ... | bash -s -- --cloud`), bash reads this very script off that
  # same stdin, and a `cat`/`read` on fd 0 mid-script races bash's own buffered read of
  # the remaining script text and can truncate it (reproduced while testing this change).
  # It would also never fire in that pipeline anyway: in `cmd1 | cmd2`, only cmd1 (curl)
  # inherits the outer stdin, so hook JSON piped to the whole pipeline never reaches bash.
  SRC=""
  PTR_DIR=$(pointer_dir) || PTR_DIR=""
  for cand in "$PTR_DIR" "${CLAUDE_PROJECT_DIR:-}" "$PWD"; do
    [ -n "$cand" ] || continue
    t=$(checkout_at "$cand") && { SRC="$t"; break; }
  done

  # cwd is not documented to be the checkout for every caller (setup script, SessionStart
  # hook), so don't rest detection on $PWD alone: fall back to a bounded, one-level-deep
  # look under the container's usual home directories. Cheap on purpose, since this runs
  # at every session start: no recursive find, stop at the first exact origin match.
  if [ -z "$SRC" ]; then
    # Search roots are fixed in production; a test harness may override them (via
    # CLAUDE_SETTINGS_SEARCH_ROOTS, space-separated) to avoid scanning this container's
    # own real checkouts under /home/user or /root.
    for root in ${CLAUDE_SETTINGS_SEARCH_ROOTS:-/home/user /root "$HOME"}; do
      [ -d "$root" ] || continue
      for child in "$root"/*; do
        [ -d "$child/.git" ] || continue
        t=$(checkout_at "$child") && { SRC="$t"; break 2; }
      done
    done
  fi
  if [ -z "$SRC" ]; then
    t=$(checkout_at "$HOME/claude-settings") && SRC="$t"
  fi

  [ -n "$SRC" ] && log "found existing checkout of $REPO at $SRC; using it as source"
fi

# Canonical path, so C:/x and /c/x compare equal. Prints nothing when DIR is empty or missing.
canon() { [ -n "$1" ] && ( cd "$1" 2>/dev/null && pwd -P ); }
# Absolute common git dir of DIR: the same for a clone and every worktree of it.
common_dir() { git -C "$1" rev-parse --path-format=absolute --git-common-dir 2>/dev/null; }
# The main working tree of the repo DIR belongs to: the first entry of the worktree list.
clone_of() { git -C "$1" worktree list --porcelain 2>/dev/null | sed -n '1s/^worktree //p'; }

# True when the pinned checkout $1 is not detached at the clone's local main commit.
pin_off_main() {
  main_commit=$(git -C "$1" rev-parse --verify -q refs/heads/main)
  git -C "$1" symbolic-ref -q HEAD >/dev/null || [ -z "$main_commit" ] \
    || [ "$(git -C "$1" rev-parse HEAD)" != "$main_commit" ]
}

# An install from a linked worktree would point the global config at a temp
# checkout. Refuse before any write, whether the source came from the script or from the cwd.
# Decision merge-reinstalls-from-main: the pinned checkout <clone>-live is the one linked
# worktree allowed, and only on a detached HEAD at the clone's local main commit. <clone>-live
# may be a link to such a worktree (merge/install_from_main.sh moves it), so paths compare resolved.
if [ -n "$SRC" ] && is_linked_worktree "$SRC"; then
  m=$(clone_of "$SRC")
  if [ -z "$m" ] || [ "$(canon "$SRC")" != "$(canon "$m-live")" ]; then
    log "ERROR: $SRC is a linked git worktree; run the installer from the main clone${m:+ $m}."
    exit 1
  fi
  if pin_off_main "$SRC"; then
    log "ERROR: the pinned checkout $SRC is not detached at local main; run merge/install_from_main.sh from the clone $m to move it."
    exit 1
  fi
fi

# put_file SRC DEST: build the file at "DEST.cs-new" in DEST's folder, then rename it over DEST, so
# DEST is never absent or half-written (a guard hook reads it at any moment). In guard.py and
# guard_*.py only, the whole placeholder line gets this run's id, the same stamp install.ps1 and its
# post-merge hook write, so hooks/guard.py can tell a half-installed set from a whole one. No other
# line is touched. STAMP_PLACEHOLDER is the same literal as $StampPlaceholder in install.ps1 (sh
# cannot share that code); an optional CR before the line end is kept. A failure leaves DEST as it
# was, is printed, and makes the run exit 1; the caller must not count the file as landed.
INSTALL_ID_VALUE="$(date +%Y%m%d%H%M%S)$$"
STAMP_PLACEHOLDER='# INSTALL_ID = "uninstalled"'
STAMP_CR="$(printf '\r')"
INSTALL_FAILED=0
# mv_retry SRC DEST: mv -f, retried 25 times at 0.1 s (the budget of Move-OverFile in install.ps1), because
# Windows refuses a rename over a file a running reader holds open. The last try's stderr is printed.
mv_retry() {
  n=1
  until mv_err=$(mv -f "$1" "$2" 2>&1); do
    if [ "$n" -ge 25 ]; then printf '%s\n' "$mv_err" >&2; return 1; fi
    n=$((n + 1)); sleep 0.1
  done
}
put_file() {
  t="$2.cs-new"
  case "$1" in
    */guard.py|*/guard_*.py)
      sed "s/^$STAMP_PLACEHOLDER\($STAMP_CR\{0,1\}\)\$/INSTALL_ID = \"$INSTALL_ID_VALUE\"\1/" "$1" > "$t" ;;
    *) cp "$1" "$t" ;;
  esac && mv_retry "$t" "$2" && return 0
  rm -f "$t"
  log "could not replace $2; left as it was"
  INSTALL_FAILED=1
  return 1
}

# ---- one install at a time, one start line and one end line in the install log --------------------
# Decision install-hooks-whole. The lock is a file made with noclobber, so only one run makes
# it. install.ps1 and its post-merge hook take the same file, so the three paths wait on each other.
# A run waits CLAUDE_SETTINGS_LOCK_WAIT seconds (default 60), then prints one line and exits 1 with
# nothing written. A lock file older than 10 minutes is a dead run's: it is removed.
# ponytail: age is the only stale test, because the lock holders live in different pid spaces
# (Windows pids and MSYS pids); an owner-alive test is the upgrade if a dead run ever needs sooner.
# The id (INSTALL_ID_VALUE, above) is unique per run: the time plus the process id. The log line
# names it with the pid.
# merge/install_from_main.sh holds the lock through its install.sh call. It writes its id into the
# lock file and passes that id as CLAUDE_SETTINGS_LOCK_TOKEN; when the two match, this run works
# under that lock: it does not wait, and it leaves the lock for its parent to remove.
INSTALL_LOG="$CLAUDE_DIR/claude-settings-install.log"
INSTALL_LOCK="$CLAUDE_DIR/.claude-settings-install.lock"
OWN_INSTALL_LOCK=1
install_log_line() { printf '%s install.sh: %s id=%s pid=%s\n' "$(date +%Y-%m-%dT%H:%M:%S)" "$1" "$INSTALL_ID_VALUE" "$$" >> "$INSTALL_LOG"; }
finish_install() {
  rc=$?
  install_log_line "end exit=$rc"
  if [ "$OWN_INSTALL_LOCK" = 1 ]; then rm -f "$INSTALL_LOCK"; fi
}
take_install_lock() {
  mkdir -p "$CLAUDE_DIR"
  if [ -n "${CLAUDE_SETTINGS_LOCK_TOKEN:-}" ] && [ "$(head -n 1 "$INSTALL_LOCK" 2>/dev/null)" = "$CLAUDE_SETTINGS_LOCK_TOKEN" ]; then
    OWN_INSTALL_LOCK=0
    trap finish_install EXIT
    install_log_line start
    return
  fi
  tries=$(( ${CLAUDE_SETTINGS_LOCK_WAIT:-60} * 5 ))
  while ! ( set -C; printf '%s\n' "$$" > "$INSTALL_LOCK" ) 2>/dev/null; do
    if [ -n "$(find "$INSTALL_LOCK" -mmin +10 2>/dev/null)" ]; then rm -f "$INSTALL_LOCK"; continue; fi
    tries=$((tries - 1))
    if [ "$tries" -le 0 ]; then
      log "ERROR: another install holds the lock $INSTALL_LOCK; nothing was changed. Run the installer again when it ends, or delete that file if no install is running."
      exit 1
    fi
    sleep 0.2
  done
  trap finish_install EXIT
  install_log_line start
}
take_install_lock

# Local install from a clone that has a branch named main: the links point at the pinned
# checkout <clone>-live, a worktree on a detached HEAD at main's commit, never at the clone,
# whose branch changes. Made here when missing; only merge/install_from_main.sh moves it. Cloud
# mode and a clone with no main branch stay unpinned.
if [ "$CLOUD" != 1 ] && [ -n "$SRC" ] && [ -e "$SRC/.git" ] && ! is_linked_worktree "$SRC"; then
  if main_commit=$(git -C "$SRC" rev-parse --verify -q refs/heads/main); then
    PIN="$SRC-live"
    if [ ! -e "$PIN" ]; then
      err=$(git -C "$SRC" worktree add -q --detach --lock --reason "claude-settings live pin" "$PIN" "$main_commit" 2>&1) \
        || { log "ERROR: cannot make the pinned checkout $PIN: $err; fix that and run the installer again."; exit 1; }
      log "made the pinned checkout $PIN at main"
    else
      pin_common=$(canon "$(common_dir "$PIN")")
      if [ -z "$pin_common" ] || [ "$pin_common" != "$(canon "$(common_dir "$SRC")")" ]; then
        log "ERROR: $PIN is not a worktree of $SRC; move it aside and run the installer again."
        exit 1
      fi
      if pin_off_main "$PIN"; then
        log "ERROR: the pinned checkout $PIN is not detached at local main; run merge/install_from_main.sh from the clone $SRC to move it."
        exit 1
      fi
      # Lock an unlocked pin, so the janitor sweep never removes it; a locked one stays as it is.
      git -C "$SRC" worktree lock --reason "claude-settings live pin" "$PIN" >/dev/null 2>&1
    fi
    SRC="$PIN"
  else
    log "WARN: $SRC has no branch named main; the links follow the clone's checked-out branch"
  fi
fi

if [ -z "$SRC" ]; then
  SRC="$HOME/claude-settings"
  mkdir -p "$SRC"
  tmp="$SRC/.tarball.tmp.tar.gz"
  if curl -fsSL "$TARBALL" -o "$tmp" && tar -xzf "$tmp" --strip-components=1 -C "$SRC"; then
    rm -f "$tmp"
  else
    rm -f "$tmp"
    log "WARN: could not fetch $TARBALL; keeping existing $SRC if present"
  fi
  for f in CLAUDE.md settings.json; do
    [ -f "$SRC/$f" ] || { log "ERROR: $SRC/$f missing, aborting"; exit 0; }
  done
fi

mkdir -p "$CLAUDE_DIR"

# A real file where land_dir()/land_skills_dir() expect a symlink is
# either a person's own pre-existing file (first local install ever: back it up) or this same
# installer's own earlier copy, left by a no-symlink-rights `ln -sfn` fallback on a prior local
# run (repeat install: no backup, per D: copy-mode-overwrites-no-backup). Content can't tell
# these apart (the source file legitimately changes between runs, e.g. a skill's SKILL.md), so
# this marker does: its absence means no local install has landed here before, so any real file
# now is a person's own and gets backed up; once it exists, every local run after the first
# treats a real file at a landed name as its own prior copy. Written once, at the end of a
# successful local run, below. (The settings.json block also reads it, only to pick the
# first-ever backup name settings.json.orig; it always backs up a plain file.)
COPY_MARKER="$CLAUDE_DIR/.claude-settings-installed"
FIRST_LOCAL_RUN=1
[ "$CLOUD" = 1 ] || [ ! -e "$COPY_MARKER" ] || FIRST_LOCAL_RUN=0

# ---- ~/.claude/CLAUDE.md : pointer -------------------------------------------------------------
# Use ~/ when the repo sits in $HOME so the same line works on any machine.
case "$SRC" in
  "$HOME"/*) POINTER="@~/${SRC#"$HOME"/}/CLAUDE.md" ;;
  *)         POINTER="@$SRC/CLAUDE.md" ;;
esac

TARGET_MD="$CLAUDE_DIR/CLAUDE.md"
if [ -f "$TARGET_MD" ] && ! grep -qx -- "$POINTER" "$TARGET_MD"; then
  BAK="$TARGET_MD.bak.$(date +%Y%m%d%H%M%S)"
  cp "$TARGET_MD" "$BAK"
  log "existing $TARGET_MD backed up to $BAK; fold anything you want to keep into $SRC/CLAUDE.md"
fi
printf '%s\n' "$POINTER" > "$TARGET_MD"
log "wrote $TARGET_MD -> $POINTER"

# land_guard_set SRC_HOOKS DEST_HOOKS: copy mode, the guard files (install-hooks-whole).
# A guard run sees the old set or the new set, never a mix. Step 1 writes every guard file, stamped
# with this run's id, and shared_names.py and git_reads.py, which the guard imports, into DEST_HOOKS/guard.d/<id>/,
# where no guard reads it yet. Step 2 replaces
# DEST_HOOKS/guard.py: the one landing that switches, because a stamped guard.py loads guard.d/<its
# id>/ (see the comment above INSTALL_ID in hooks/guard.py). Step 3 lands the flat guard_*.py, kept
# beside it for tools that read them by path. The folder of the set before this one stays until the
# next install; older ones go. A step 1 failure removes the new folder and lands nothing: the old
# set stays whole and the run exits 1.
land_guard_set() {
  gdir="$2/guard.d/$INSTALL_ID_VALUE"
  prev_id=$(sed -n 's/^INSTALL_ID = "\([^"]*\)".*/\1/p' "$2/guard.py" 2>/dev/null | head -n1)
  mkdir -p "$gdir" || { log "could not make $gdir; the guard files stay as they were"; INSTALL_FAILED=1; return 1; }
  for gf in "$1"/guard.py "$1"/guard_*.py "$1"/shared_names.py "$1"/git_reads.py; do
    [ -f "$gf" ] || continue
    put_file "$gf" "$gdir/$(basename "$gf")" || { rm -rf "$gdir"; log "the guard files stay as they were"; return 1; }
  done
  [ -f "$1/guard.py" ] && { put_file "$1/guard.py" "$2/guard.py" || { rm -rf "$gdir"; return 1; }; }
  for gf in "$1"/guard_*.py; do [ -f "$gf" ] && put_file "$gf" "$2/$(basename "$gf")"; done
  for gd in "$2"/guard.d/*; do
    [ -d "$gd" ] || continue
    case "$(basename "$gd")" in "$INSTALL_ID_VALUE"|"$prev_id") ;; *) rm -rf "$gd" ;; esac
  done
  return 0
}

# ---- ~/.claude/agents and ~/.claude/lint --------------------------------------------------------
# agents/: one file per role (builder, reviewer). lint/: the STE linter and the report guard.
# Local: per-file symlink. Cloud: copy.
#
# Local mode also prunes: after landing every file the source defines now, it removes a
# destination entry that this same function linked on an earlier run, for a source file
# that has since gone away. Without this, "$DEST_DIR" holds the UNION of every file that
# has ever existed in "$SRC/$sub" across every install, not the set the current ref
# defines. A prune candidate must pass all three tests: it is a symlink (never a regular
# file, so a person's own file is never touched), its target sits inside "$SRC/$sub"
# (never a symlink land_dir did not create, so a hand-made link elsewhere is left alone),
# and that target no longer exists (so a live link is left alone too). A ".bak.*" file
# this function writes below is a regular file, so it already fails the first test.
#
# Cloud mode does not prune. A cloud install copies bytes, not links, so a landed file
# in "$DEST_DIR" carries no mark of which source file made it or whether that source
# still exists. Proving a copy is stale needs a manifest recording what the last run
# landed, kept outside "$DEST_DIR" so the copies cannot corrupt the record that would
# prune them. That manifest is a real feature, not a line fix, and is left for a
# separate change. Until then, cloud mode accumulates stale copies for any source file
# removed after a cloud install has run: a real file with stale content, and it never
# dangles, so no "[ -f ]" hook guard catches it either.
land_dir() {
  sub="$1"
  DEST_DIR="$CLAUDE_DIR/$sub"
  mkdir -p "$DEST_DIR"
  LANDED=""
  GUARD_SET=0; GUARD_OK=0
  if [ "$CLOUD" = 1 ] && [ "$sub" = hooks ]; then
    GUARD_SET=1
    land_guard_set "$SRC/hooks" "$DEST_DIR" && GUARD_OK=1
  fi
  for f in "$SRC/$sub"/*; do
    [ -f "$f" ] || continue
    # The guard files landed above, as one set.
    case "$(basename "$f")" in
      guard.py|guard_*.py)
        if [ "$GUARD_SET" = 1 ]; then [ "$GUARD_OK" = 1 ] && LANDED="$LANDED $(basename "$f")"; continue; fi ;;
    esac
    DEST="$DEST_DIR/$(basename "$f")"
    if [ "$CLOUD" = 1 ]; then
      put_file "$f" "$DEST" || continue
    else
      if [ -L "$DEST" ] && [ "$(readlink "$DEST")" = "$f" ]; then LANDED="$LANDED $(basename "$f")"; continue; fi
      # A real file at DEST (not a symlink): on the first local install ever, it is a
      # person's own file, backed up. After that, a real file here is this same
      # installer's own earlier copy (`ln -sfn` fell back to copying it on a
      # no-symlink-rights machine): replace it, no backup (D: copy-mode-overwrites-no-backup).
      if [ -e "$DEST" ] && [ ! -L "$DEST" ]; then
        if [ "$FIRST_LOCAL_RUN" = 1 ]; then
          BAK="$DEST.bak.$(date +%Y%m%d%H%M%S)"
          mv "$DEST" "$BAK"
          log "existing $DEST moved to $BAK"
        else
          rm -f "$DEST"
        fi
      fi
      ln -sfn "$f" "$DEST"
    fi
    LANDED="$LANDED $(basename "$f")"
  done
  [ -n "$LANDED" ] && log "$sub in $DEST_DIR:$LANDED"
  if [ "$CLOUD" != 1 ]; then
    PRUNED=""
    for d in "$DEST_DIR"/*; do
      [ -L "$d" ] || continue
      target=$(readlink "$d")
      case "$target" in
        "$SRC/$sub"/*) ;;
        *) continue ;;
      esac
      [ -e "$target" ] && continue
      rm -f "$d"
      PRUNED="$PRUNED $(basename "$d")"
    done
    [ -n "$PRUNED" ] && log "$sub in $DEST_DIR: pruned (source removed):$PRUNED"
  fi
}

# Skill backups never land inside skills/ or any folder Claude Code scans: a backup there loads as
# one more skill, and cloud runs install at every resume and merge. They go to
# "$CLAUDE_DIR/backups/skills/<name>.<time>". A backup is moved there, never deleted.
SKILL_BAK_DIR="$CLAUDE_DIR/backups/skills"
# What a cloud run last copied into skills/<name>, as a tree hash, kept outside skills/.
SKILL_COPY_DIR="$CLAUDE_DIR/backups/skill-copies"

# Print a hash of a directory tree: every file path and every file content.
# It covers file names and contents only, so a mode, empty-folder or symlink-only change is replaced with no backup.
tree_hash() {
  [ -d "$1" ] || return 1
  ( cd "$1" && find . -type f | LC_ALL=C sort | while IFS= read -r f; do
      printf '%s ' "$f"; sha256_of < "$f"
    done ) | sha256_of
}
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum; else shasum -a 256; fi | awk '{print $1}'
}

# Move $1 to the skill backup folder as $2.<time>. A name that is taken gets the pid added.
backup_skill() {
  mkdir -p "$SKILL_BAK_DIR"
  BAK="$SKILL_BAK_DIR/$2.$(date +%Y%m%d%H%M%S)"
  [ ! -e "$BAK" ] || BAK="$BAK.$$"
  mv "$1" "$BAK"
  log "existing $1 moved to $BAK"
}

# An older installer left skills/<name>.bak.<time> folders. Move each out of skills/.
move_old_skill_baks() {
  for old in "$DEST_DIR"/*.bak.[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]; do
    [ -d "$old" ] && [ ! -L "$old" ] || continue
    bn=$(basename "$old")
    mkdir -p "$SKILL_BAK_DIR"
    to="$SKILL_BAK_DIR/$bn"
    [ ! -e "$to" ] || to="$to.$$"
    mv "$old" "$to"
    log "old backup $old moved to $to"
  done
}

# skills/ lands differently from land_dir(): each skills/<name>/ is ONE whole-directory
# symlink, ~/.claude/skills/<name> -> <clone>/skills/<name>, not a per-file symlink. The
# skills docs allow a skill entry to be "a symlink to a directory elsewhere on disk". A
# per-file loop like land_dir()'s `for f in "$SRC/$sub"/*; do [ -f "$f" ] || continue` would
# skip every skill subdirectory outright, so a landed skill never appeared under
# ~/.claude/skills at all; that is the defect this function exists to not have.
#
# A pre-existing entry this repo does NOT ship (a person's own skill) is never touched: the
# loop only ever looks at names under "$SRC/skills", so a name absent there is never a
# candidate, never backed up, never pruned.
land_skills_dir() {
  DEST_DIR="$CLAUDE_DIR/skills"
  mkdir -p "$DEST_DIR"
  move_old_skill_baks
  LANDED=""
  for d in "$SRC/skills"/*; do
    [ -d "$d" ] || continue
    name=$(basename "$d")
    DEST="$DEST_DIR/$name"
    if [ "$CLOUD" = 1 ]; then
      # Our own earlier copy is replaced with no backup. It is ours when its tree hash is the
      # one recorded at the last copy (the source may have changed since), or when it equals
      # the source. Anything else is a hand edit or a person's skill: back it up.
      if [ -e "$DEST" ] || [ -L "$DEST" ]; then
        have=$(tree_hash "$DEST"); rec=$(cat "$SKILL_COPY_DIR/$name" 2>/dev/null)
        if [ -n "$have" ] && { [ "$have" = "$rec" ] || [ "$have" = "$(tree_hash "$d")" ]; }; then
          rm -rf "$DEST"
        else
          backup_skill "$DEST" "$name"
        fi
      fi
      cp -r "$d" "$DEST"
      mkdir -p "$SKILL_COPY_DIR"
      tree_hash "$DEST" > "$SKILL_COPY_DIR/$name"
    else
      if [ -L "$DEST" ] && [ "$(readlink "$DEST")" = "$d" ]; then LANDED="$LANDED $name"; continue; fi
      # A real directory at DEST (not a symlink): on the first local install ever, it is a
      # person's own hand-made skill, backed up. After that, a real directory here is this
      # same installer's own earlier copy, from a no-symlink-rights machine where `ln -sfn`
      # fell back to copying it: replace it, no backup (D: copy-mode-overwrites-no-backup).
      if [ -e "$DEST" ] && [ ! -L "$DEST" ]; then
        if [ "$FIRST_LOCAL_RUN" = 1 ]; then
          backup_skill "$DEST" "$name"
        else
          rm -rf "$DEST"
        fi
      fi
      ln -sfn "$d" "$DEST"
    fi
    LANDED="$LANDED $name"
  done
  [ -n "$LANDED" ] && log "skills in $DEST_DIR:$LANDED"
  if [ "$CLOUD" != 1 ]; then
    PRUNED=""
    for e in "$DEST_DIR"/*; do
      [ -L "$e" ] || continue
      target=$(readlink "$e")
      case "$target" in
        "$SRC/skills"/*) ;;
        *) continue ;;
      esac
      [ -e "$target" ] && continue
      rm -f "$e"
      PRUNED="$PRUNED $(basename "$e")"
    done
    [ -n "$PRUNED" ] && log "skills in $DEST_DIR: pruned (source removed):$PRUNED"
  fi
}
# The set of directories landed above comes from landed-dirs.txt at the repo root, the single
# source install.ps1 reads too (see the comment there). hooks/guard.py's CONFIG_FROZEN_DIRS is a
# deliberately separate literal; see the comment beside it in hooks/guard.py for why.
# lint/check_landed_dirs.py checks the two stay in agreement.
while IFS= read -r sub || [ -n "$sub" ]; do
  sub=$(printf '%s' "$sub" | tr -d '\r' | sed 's/#.*//; s/^[[:space:]]*//; s/[[:space:]]*$//')
  [ -n "$sub" ] || continue
  if [ "$sub" = "skills" ]; then land_skills_dir; else land_dir "$sub"; fi
done < "$SRC/landed-dirs.txt"

# A folder an earlier install landed and the repo has since moved: ux, now docs/design (decision
# ux-house-rules). Local mode removes its dangling links into "$SRC/ux", the same test land_dir
# prunes with, then the folder once it is empty. A person's own file and a cloud copy stay, as land_dir leaves them.
sub=ux
DEST_DIR="$CLAUDE_DIR/$sub"
if [ -d "$DEST_DIR" ] && [ ! -L "$DEST_DIR" ] && [ "$CLOUD" != 1 ]; then
  for d in "$DEST_DIR"/*; do
    [ -L "$d" ] || continue
    case "$(readlink "$d")" in "$SRC/$sub"/*) ;; *) continue ;; esac
    [ -e "$d" ] && continue
    rm -f "$d"
  done
  if [ -z "$(ls -A "$DEST_DIR")" ]; then rmdir "$DEST_DIR" && log "removed $DEST_DIR (the repo no longer lands it)"; fi
fi

# Packages that a skill loads (typescript, for plain-english-map): one `npm ci` in the clone root.
# A skill is linked, so its real path is in the clone, and it finds the clone's node_modules. A failure
# is logged and never fails the install. A cloud copy of a skill sits outside the clone, so cloud skips this.
if [ "$CLOUD" != 1 ] && [ -f "$SRC/package-lock.json" ]; then
  if command -v npm >/dev/null 2>&1; then
    if npm_out=$(cd "$SRC" && npm ci --ignore-scripts --no-audit --no-fund 2>&1); then
      log "npm ci ran in $SRC"
    else
      log "WARNING: npm ci failed in $SRC; the plain-english-map skill cannot load typescript until it passes. Last lines of its output:"
      printf '%s\n' "$npm_out" | tail -n 5 | while IFS= read -r l; do log "  $l"; done
    fi
  else
    log "WARNING: npm not found; run npm ci in $SRC so the plain-english-map skill can load typescript"
  fi
fi

# Stale files from the old Banchi janitor. Nothing runs them, and bin/claude-janitor now runs
# janitor/sweep.py. Only these exact names are removed, and only when they are not a link into
# this repo's bin/. Nothing else under bin/ is ever touched.
for stale in janitor.py reap.py session-teardown.sh; do
  f="$CLAUDE_DIR/bin/$stale"
  [ -e "$f" ] || [ -L "$f" ] || continue
  if [ -L "$f" ]; then
    case "$(readlink "$f")" in "$SRC/bin"/*) continue ;; esac
  fi
  rm -f "$f" && log "removed stale $f (old janitor, nothing runs it)"
done

# ---- ~/.claude/settings.json ------------------------------------------------------------------
TARGET_JSON="$CLAUDE_DIR/settings.json"

if [ "$CLOUD" = 1 ]; then
  # Cloud: generate a real file (not a symlink) and add a SessionStart hook that refreshes
  # both files from GitHub at every session start/resume. Only in cloud, so the shared
  # settings.json stays hook-free for Windows/macOS/Linux locals.
  HOOK_CMD="curl -fsSL ${RAW}/install.sh | bash -s -- --cloud"
  if command -v jq >/dev/null 2>&1; then
    jq --arg cmd "$HOOK_CMD" \
      '.hooks.SessionStart = [{"matcher":"startup|resume","hooks":[{"type":"command","command":$cmd,"timeout":60}]}]' \
      "$SRC/settings.json" > "$TARGET_JSON.tmp" && mv "$TARGET_JSON.tmp" "$TARGET_JSON"
    log "wrote $TARGET_JSON (repo settings + cloud refresh hook)"
  else
    cp "$SRC/settings.json" "$TARGET_JSON"
    log "wrote $TARGET_JSON (jq missing, no refresh hook added)"
  fi
else
  # Local: symlink, so `git pull` in the clone is the whole update.
  if [ -L "$TARGET_JSON" ] && [ "$(readlink "$TARGET_JSON")" = "$SRC/settings.json" ]; then
    log "$TARGET_JSON already links to $SRC/settings.json"
  else
    # A real file here (not a symlink): on the first local install ever, it is a person's
    # own settings.json; after that, a real file may be this installer's own earlier copy
    # (a no-symlink-rights machine where `ln -sfn` fell back to copying). Either way it is
    # backed up, and only the newest settings.json.bak.<time>.<pid> stays. This is the one exception to
    # D: copy-mode-overwrites-no-backup; skill and agent copies are still replaced with no backup.
    if [ -e "$TARGET_JSON" ] && [ ! -L "$TARGET_JSON" ]; then
      # The first-ever backup is settings.json.orig, kept for good (never overwritten, never
      # pruned). Any other backup is settings.json.bak.<time>.<pid>, and only the newest stays.
      PRUNE=1; BAK="$TARGET_JSON.bak.$(date +%Y%m%d%H%M%S).$$"
      if [ "$FIRST_LOCAL_RUN" = 1 ] && [ ! -e "$TARGET_JSON.orig" ]; then PRUNE=0; BAK="$TARGET_JSON.orig"; fi
      mv "$TARGET_JSON" "$BAK" || { log "ERROR: cannot move $TARGET_JSON to $BAK; nothing linked"; exit 1; }
      if [ "$PRUNE" = 1 ]; then
        for old in "$TARGET_JSON".bak.*.*; do [ "$old" = "$BAK" ] || rm -f "$old"; done
      fi
      log "existing $TARGET_JSON moved to $BAK; merge any keys you want into $SRC/settings.json"
    fi
    ln -sfn "$SRC/settings.json" "$TARGET_JSON"
    log "linked $TARGET_JSON -> $SRC/settings.json"
  fi
fi

# ~/.claude/bin on PATH, once, in the rc file of the login shell.
case "${SHELL:-}" in *zsh) RC="$HOME/.zshrc" ;; *) RC="$HOME/.bashrc" ;; esac
if [ "$CLOUD" != 1 ] && ! grep -qsF '# claude-settings: ~/.claude/bin on PATH' "$RC"; then
  printf '\n# claude-settings: ~/.claude/bin on PATH\nexport PATH="$HOME/.claude/bin:$PATH"\n' >> "$RC"
  log "added ~/.claude/bin to PATH in $RC; a new session picks it up"
fi

# Marks a local install has landed here, so the NEXT local run treats a real file/dir at a
# landed name as its own earlier copy rather than a person's. See the comment above its
# definition.
[ "$CLOUD" = 1 ] || : > "$COPY_MARKER"

exit "$INSTALL_FAILED"
