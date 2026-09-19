#!/usr/bin/env bash
# Wire ~/.claude to the files in this repo. Linux/macOS local, and Claude Code cloud sessions.
#
#   Local (from a clone):   bash install.sh
#   Cloud setup script:     curl -fsSL https://raw.githubusercontent.com/shivinate7/claude-settings/main/install.sh | bash -s -- --cloud
#
# What it does:
#   ~/.claude/CLAUDE.md      -> one-line pointer: @<repo>/CLAUDE.md
#   ~/.claude/agents/*.md    -> role definitions (builder, reviewer): local symlinks, cloud copies
#   ~/.claude/lint/*         -> STE linter + hook gate: local symlinks, cloud copies
#   ~/.claude/hooks/*        -> PreToolUse guard + session-start line: local symlinks, cloud copies
#   ~/.claude/settings.json  -> local: symlink to <repo>/settings.json
#                               cloud: generated copy of settings.json plus a SessionStart hook
#                                      that re-runs this script, so every new cloud session pulls
#                                      the latest files from GitHub.
set -u

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
  case "$d" in
    "~"/*) d="$HOME${d#\~}" ;;
  esac
  [ -n "$d" ] && [ -d "$d" ] || return 1
  printf '%s' "$d"
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

# ---- ~/.claude/agents and ~/.claude/lint --------------------------------------------------------
# agents/: one file per role (builder, reviewer). lint/: the STE linter and its hook gate.
# Local: per-file symlink. Cloud: copy.
land_dir() {
  sub="$1"
  DEST_DIR="$CLAUDE_DIR/$sub"
  mkdir -p "$DEST_DIR"
  LANDED=""
  for f in "$SRC/$sub"/*; do
    [ -f "$f" ] || continue
    DEST="$DEST_DIR/$(basename "$f")"
    if [ "$CLOUD" = 1 ]; then
      cp "$f" "$DEST"
    else
      if [ -L "$DEST" ] && [ "$(readlink "$DEST")" = "$f" ]; then LANDED="$LANDED $(basename "$f")"; continue; fi
      if [ -e "$DEST" ] && [ ! -L "$DEST" ]; then
        BAK="$DEST.bak.$(date +%Y%m%d%H%M%S)"
        mv "$DEST" "$BAK"
        log "existing $DEST moved to $BAK"
      fi
      ln -sfn "$f" "$DEST"
    fi
    LANDED="$LANDED $(basename "$f")"
  done
  [ -n "$LANDED" ] && log "$sub in $DEST_DIR:$LANDED"
}
land_dir agents
land_dir lint
land_dir hooks

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
    if [ -e "$TARGET_JSON" ] && [ ! -L "$TARGET_JSON" ]; then
      BAK="$TARGET_JSON.bak.$(date +%Y%m%d%H%M%S)"
      mv "$TARGET_JSON" "$BAK"
      log "existing $TARGET_JSON moved to $BAK; merge any keys you want into $SRC/settings.json"
    fi
    ln -sfn "$SRC/settings.json" "$TARGET_JSON"
    log "linked $TARGET_JSON -> $SRC/settings.json"
  fi
fi

exit 0
