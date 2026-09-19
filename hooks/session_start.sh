#!/bin/sh
# Prints "checkout <toplevel> on <branch>, <n> dirty files" at session start and resume.
# Silent outside a git tree or when git is missing. Always exits 0, nothing on stderr.

input=$(cat 2>/dev/null)
cwd=$(printf '%s' "$input" | sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
[ -n "$cwd" ] || cwd=$(pwd)

command -v git >/dev/null 2>&1 || exit 0

toplevel=$(cd "$cwd" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)
[ -n "$toplevel" ] || exit 0

branch=$(cd "$cwd" 2>/dev/null && git rev-parse --abbrev-ref HEAD 2>/dev/null)
[ "$branch" = "HEAD" ] && branch="detached"

n=$(cd "$cwd" 2>/dev/null && git status --porcelain 2>/dev/null | wc -l | tr -d '[:space:]')

printf 'checkout %s on %s, %s dirty files\n' "$toplevel" "$branch" "$n"

# Divergence check: does ~/.claude/CLAUDE.md's pointer target match this checkout's CLAUDE.md?
# Same parsing as settings.json's refresh hook. Silent on any missing/unreadable piece.
config_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
global_md="$config_dir/CLAUDE.md"
if [ -f "$global_md" ]; then
  d=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$global_md" 2>/dev/null | head -n1)
  case "$d" in
    "~"/*) d="$HOME${d#\~}" ;;
  esac
  if [ -n "$d" ] && [ -f "$d/CLAUDE.md" ] && [ -f "$toplevel/CLAUDE.md" ]; then
    pointer_target="$d/CLAUDE.md"
    checkout_md="$toplevel/CLAUDE.md"
    same_path=0
    rp="$(cd "$(dirname "$pointer_target")" 2>/dev/null && pwd)/CLAUDE.md"
    rc="$(cd "$(dirname "$checkout_md")" 2>/dev/null && pwd)/CLAUDE.md"
    [ -n "$rp" ] && [ -n "$rc" ] && [ "$rp" = "$rc" ] && same_path=1
    if [ "$same_path" != 1 ] && ! cmp -s "$pointer_target" "$checkout_md" 2>/dev/null; then
      printf 'claude-settings: global rules at %s differ from this checkout at %s\n' "$pointer_target" "$checkout_md"
    fi
  fi
fi

# The pointer checkout's HEAD must be `main`. `~/.claude/lint/*`, `~/.claude/hooks/*` and
# `~/.claude/agents/*` are symlinks into that one checkout, so its branch decides which copy
# of the rules and the gates every session on this machine runs. A branch left checked out
# there makes unreviewed work live everywhere, silently. Reported here, never fixed here: a
# branch switch is a whole-tree act and another session may be working in it.
if [ -n "$d" ] && [ -d "$d/.git" ]; then
  pointer_branch=$(cd "$d" 2>/dev/null && git rev-parse --abbrev-ref HEAD 2>/dev/null)
  if [ -n "$pointer_branch" ] && [ "$pointer_branch" != "main" ]; then
    printf 'claude-settings: %s is on %s, not main; global rules and hooks are that branch\n' \
      "$d" "$pointer_branch"
  fi
fi

exit 0
