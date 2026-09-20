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
#
# This only means something when $toplevel is itself a second clone of the same repo the
# pointer names, for example a lane worktree. In any other repo, the pointer's CLAUDE.md and
# the checkout's CLAUDE.md differ by design, so the raw file compare below is gated on both
# trees sharing one origin. Read the origin fails closed: either remote missing or unreadable
# means silence, never a printed line.
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
    if [ "$same_path" != 1 ]; then
      pointer_origin=$(cd "$d" 2>/dev/null && git remote get-url origin 2>/dev/null)
      checkout_origin=$(cd "$toplevel" 2>/dev/null && git remote get-url origin 2>/dev/null)
      if [ -n "$pointer_origin" ] && [ -n "$checkout_origin" ] \
         && [ "$pointer_origin" = "$checkout_origin" ] \
         && ! cmp -s "$pointer_target" "$checkout_md" 2>/dev/null; then
        printf 'claude-settings: global rules at %s differ from this checkout at %s\n' "$pointer_target" "$checkout_md"
      fi
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

  # Freshness check, only when the pointer clone is on main.
  #
  # main..origin/main reads the local remote-tracking ref, which is only as
  # fresh as the last fetch. A stale ref would report "0 behind" on a machine
  # that is actually behind, so we fetch first, refs only, with a short
  # background timeout. This adds a small network read at every session
  # start, and up to about 2 seconds of latency when the network is slow.
  #
  # The fetch can fail or be killed by the timeout. Either way is a read
  # that did not run, never a clean "0 behind". We capture the fetch's own
  # exit status and branch on it: 0 means it ran, anything else (a git
  # failure or the timeout's kill) means we do not know, and we say so
  # instead of staying silent, which would read as "up to date".
  #
  # CLAUDE_SETTINGS_FETCH_TIMEOUT overrides the 2 second bound, for tests.
  if [ "$pointer_branch" = "main" ]; then
    fetch_timeout="${CLAUDE_SETTINGS_FETCH_TIMEOUT:-2}"
    ( cd "$d" 2>/dev/null && git fetch --quiet origin main >/dev/null 2>&1 ) &
    fetch_pid=$!
    ( sleep "$fetch_timeout"; kill "$fetch_pid" >/dev/null 2>&1 ) >/dev/null 2>&1 &
    killer_pid=$!
    wait "$fetch_pid" 2>/dev/null
    fetch_rc=$?
    kill "$killer_pid" >/dev/null 2>&1
    wait "$killer_pid" 2>/dev/null

    if [ "$fetch_rc" -eq 0 ] 2>/dev/null; then
      behind=$(cd "$d" 2>/dev/null && git rev-list --count main..origin/main 2>/dev/null)
      if [ -n "$behind" ] && [ "$behind" -gt 0 ] 2>/dev/null; then
        printf 'claude-settings: %s is %s commits behind origin/main; global rules and hooks are stale\n' \
          "$d" "$behind"
      fi
    else
      printf 'claude-settings: cannot check %s against origin/main, the fetch did not run; freshness unknown\n' \
        "$d"
    fi
  fi
fi

exit 0
