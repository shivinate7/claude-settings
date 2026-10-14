#!/bin/sh
# Pulls the claude-settings clone and runs its install.sh, at session start and resume.
# Finds the clone through the @ pointer in the global CLAUDE.md. Exits at once in cloud sessions.
# A failed pull or install falls through, and the script always exits 0.

[ -n "$CLAUDE_CODE_REMOTE" ] && exit 0
d=$(sed -n "s|^@\(.*\)/CLAUDE\.md$|\1|p" "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md" | head -n1)
case "$d" in "~"/*) d="$HOME${d#\~}";; esac
[ -n "$d" ] && [ -d "$d/.git" ] && git -C "$d" pull -q --ff-only >/dev/null 2>&1
[ -f "$d/install.sh" ] && command -v bash >/dev/null 2>&1 && bash "$d/install.sh" >/dev/null 2>&1
exit 0
