#!/usr/bin/env bash
# Wire ~/.claude to the files in this repo. Linux/macOS local, and Claude Code cloud sessions.
#
#   Local (from a clone):   bash install.sh
#   Cloud setup script:     curl -fsSL https://raw.githubusercontent.com/ssemwal-cdc/claude-settings/main/install.sh | bash -s -- --cloud
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

REPO="ssemwal-cdc/claude-settings"
REF="${CLAUDE_SETTINGS_REF:-main}"
RAW="https://raw.githubusercontent.com/${REPO}/${REF}"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

CLOUD=0
[ "${1:-}" = "--cloud" ] && CLOUD=1
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] && CLOUD=1

log() { printf 'claude-settings: %s\n' "$*"; }

# Locate the source files: the clone this script lives in, else fetch from GitHub.
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/CLAUDE.md" ] && [ -f "$SCRIPT_DIR/settings.json" ]; then
  SRC="$SCRIPT_DIR"
else
  SRC="$HOME/claude-settings"
  mkdir -p "$SRC"
  mkdir -p "$SRC/agents" "$SRC/lint" "$SRC/hooks"
  for f in CLAUDE.md settings.json agents/builder.md agents/reviewer.md \
           lint/ste_lint.py lint/ste_gate.py lint/report_gate.py lint/LICENSE-ste_lint \
           hooks/guard.py hooks/session_start.sh hooks/test_guard.py; do
    if curl -fsSL "$RAW/$f" -o "$SRC/$f.tmp"; then
      mv "$SRC/$f.tmp" "$SRC/$f"
    else
      rm -f "$SRC/$f.tmp"
      log "WARN: could not fetch $RAW/$f; keeping existing $SRC/$f if present"
    fi
  done
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
