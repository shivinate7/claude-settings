#!/bin/sh
# Prints "checkout <toplevel> on <branch>, <n> dirty files" at session start and resume. Also warns when core.worktree is set in the shared git config, the global rules differ from this checkout, the claude-settings clone is off main or behind origin/main, this repo's default branch is behind origin, more than 50 agent worktrees exist, a freshness check could not run, or the SessionEnd sweep is disarmed or unknown. Prints the repo's caution level with its facts and acts, or says it is unknown.
# Outside a git tree or when git is missing, prints only the cloud tier line. Always exits 0, nothing on stderr.

input=$(cat 2>/dev/null)
cwd=$(printf '%s' "$input" | sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
[ -n "$cwd" ] || cwd=$(pwd)

# tier_line: cloud sessions only (the CLAUDE_CODE_REMOTE read install.sh makes), tell the session how
# to find its tier (decision session-tiers). One call runs per run: at the no-git or no-toplevel exit,
# or right after the checkout line, so a cloud session gets it in any folder. The hook cannot read the
# tier itself: get_session and list_sessions are MCP tools only, and a hook never calls the sessions API
# with a token. Cost: one env read, no network, no new process, no timer, no file written.
tier_line() {
  if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
    printf '%s\n' 'session tier: read your own record with get_session (no session_id). A parent_session_id means you are a child of that session, and your cs-build:<tier> tag is your tier. No parent: pick solo, one lane or coordinator from the request. Before you act as coordinator, read every page of list_sessions for a session tagged both cs-build:coordinator and cs-repo:<owner>/<name> for this repo whose session_status is not archived; if one is found, coordinate with it, else proceed. Merge role: this sentence is for a session whose own tag is cs-build:coordinator or cs-build:batch-runner, and for no other. Such a session runs `~/.claude/bin/merge --role <tier>` (its own tier) at session start and again after each resume, because a fresh container loses the role file. A lane or any other tier never runs it, and this line is no instruction to it.'
  fi
}

command -v git >/dev/null 2>&1 || { tier_line; exit 0; }

# bounded_git <dir> <outfile> <git args...>: runs git in <dir>, stdout to <outfile>, killed after
# CLAUDE_SETTINGS_FETCH_TIMEOUT seconds (default 2). Returns git's status, or a kill's (above 1)
# when the bound hit. The one home for every bounded git call below.
bounded_git() {
  fetch_timeout="${CLAUDE_SETTINGS_FETCH_TIMEOUT:-2}"
  git_dir_arg="$1"
  git_out_arg="$2"
  shift 2
  ( cd "$git_dir_arg" 2>/dev/null && git "$@" >"$git_out_arg" 2>/dev/null ) &
  fetch_pid=$!
  ( sleep "$fetch_timeout"; kill "$fetch_pid" >/dev/null 2>&1 ) >/dev/null 2>&1 &
  killer_pid=$!
  wait "$fetch_pid" 2>/dev/null
  fetch_rc=$?
  kill "$killer_pid" >/dev/null 2>&1
  wait "$killer_pid" 2>/dev/null
  return "$fetch_rc"
}

# bounded_fetch <dir> <branch>: quiet `git fetch origin <branch>` in <dir>, bounded. Returns the
# fetch's status: 0 ran, else not. The one home for both freshness checks below.
bounded_fetch() {
  bounded_git "$1" /dev/null fetch --quiet origin "$2"
}

toplevel=$(cd "$cwd" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)
[ -n "$toplevel" ] || { tier_line; exit 0; }

branch=$(cd "$cwd" 2>/dev/null && git rev-parse --abbrev-ref HEAD 2>/dev/null)
[ "$branch" = "HEAD" ] && branch="detached"

n=$(cd "$cwd" 2>/dev/null && git status --porcelain 2>/dev/null | wc -l | tr -d '[:space:]')

printf 'checkout %s on %s, %s dirty files\n' "$toplevel" "$branch" "$n"
tier_line

# core.worktree in the SHARED config re-points every checkout of the clone at one tree. A child
# `git init` that inherits GIT_DIR and GIT_WORK_TREE writes it.
# Warns only, never fixes: the value may be someone's live work. Both git calls are bounded, so a
# slow git never stalls session start. `git config` exits 0 when the key is set, 1 when it is
# absent, and above 1 when the read failed or was killed, which is reported as unknown, never as
# clear. A submodule sets this key on purpose, so it is skipped.
cw_out=$(mktemp 2>/dev/null)
if [ -n "$cw_out" ]; then
  if bounded_git "$cwd" "$cw_out" rev-parse --show-superproject-working-tree; then
    if [ -z "$(cat "$cw_out" 2>/dev/null)" ]; then
      bounded_git "$cwd" "$cw_out" config --local --get core.worktree
      core_worktree_rc=$?
      if [ "$core_worktree_rc" -eq 0 ]; then
        printf 'checkout %s: core.worktree is set to %s in the shared git config; every checkout of this clone reads that tree. Unset it with git config --local --unset core.worktree\n' \
          "$cwd" "$(cat "$cw_out" 2>/dev/null)"
      elif [ "$core_worktree_rc" -gt 1 ]; then
        printf 'checkout %s: cannot read core.worktree from the git config; its state is unknown\n' "$cwd"
      fi
    fi
  else
    printf 'checkout %s: cannot read core.worktree from the git config; its state is unknown\n' "$cwd"
  fi
  rm -f "$cw_out" 2>/dev/null
fi

# Divergence check: does ~/.claude/CLAUDE.md's pointer target match this checkout's CLAUDE.md?
# Same parsing as settings.json's refresh hook. Silent on any missing/unreadable piece.
#
# This only means something when $toplevel is itself a second clone of the same repo the
# pointer names, for example a lane worktree. In any other repo, the pointer's CLAUDE.md and
# the checkout's CLAUDE.md differ by design, so the raw file compare below runs only on both
# trees sharing one origin. Read the origin fails closed: either remote missing or unreadable
# means silence, never a printed line.
config_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
global_md="$config_dir/CLAUDE.md"
if [ -f "$global_md" ]; then
  d=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$global_md" 2>/dev/null | head -n1)
  # SC2088: the pattern is the literal two characters "~/" that the pointer line holds, never an expansion.
  # shellcheck disable=SC2088
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
# of the rules and the guards every session on this machine runs. A branch left checked out
# there makes unreviewed work live everywhere, silently. Reported here, never fixed here: a
# branch switch is a whole-tree act and another session may be working in it.
# `.git` is a directory in a full clone and a file in a linked worktree (the pinned `<clone>-live`).
# A checkout detached at local main's commit counts as on main; detached anywhere else is off main.
if [ -n "$d" ] && [ -e "$d/.git" ]; then
  pointer_branch=$(cd "$d" 2>/dev/null && git rev-parse --abbrev-ref HEAD 2>/dev/null)
  if [ "$pointer_branch" = "HEAD" ]; then
    pin_head=$(cd "$d" 2>/dev/null && git rev-parse HEAD 2>/dev/null)
    main_head=$(cd "$d" 2>/dev/null && git rev-parse --verify -q refs/heads/main 2>/dev/null)
    if [ -n "$pin_head" ] && [ "$pin_head" = "$main_head" ]; then
      pointer_branch=main
    else
      pointer_branch="a detached HEAD"
    fi
  fi
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
  #
  # A clone install.sh made (claude-settings.cloudMirror) is refreshed by install.sh in the same
  # session start, so a behind count on it is a false alarm. The check skips it.
  cloud_mirror=$(cd "$d" 2>/dev/null && git config --get claude-settings.cloudMirror 2>/dev/null)
  if [ "$pointer_branch" = "main" ] && [ "$cloud_mirror" != "true" ]; then
    if bounded_fetch "$d" main; then
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

# The repo's caution level, once per session: its facts and expected acts, so the session reads them and
# never infers them. lint/layout.py caution is the one home (decision repo-kind-and-caution). A read that
# cannot run is reported as unknown, never as a level. One python start, no file written.
if [ -n "$d" ] && [ -f "$d/lint/layout.py" ]; then
  if command -v python3 >/dev/null 2>&1; then
    caution_text=$(python3 "$d/lint/layout.py" caution "$toplevel" 2>/dev/null) || caution_text=""
  else
    caution_text=""
  fi
  if [ -n "$caution_text" ]; then
    printf '%s\n' "$caution_text" | sed 's/^/repo /'
  else
    printf 'repo caution: unknown, the level could not be read\n'
  fi
fi

# The session's own repo: when its default branch is checked out and behind origin, say so.
# Skipped for the claude-settings clone, whose line above already covers it. Never pulls;
# the fetch never moves a local branch (it may write FETCH_HEAD and remote-tracking refs). Unset origin/HEAD means no line.
default_branch=$(cd "$toplevel" 2>/dev/null && git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null)
default_branch="${default_branch#origin/}"
if [ -n "$default_branch" ] && [ "$branch" = "$default_branch" ] \
   && { [ -z "$d" ] || [ "$(cd "$toplevel" 2>/dev/null && pwd -P)" != "$(cd "$d" 2>/dev/null && pwd -P)" ]; }; then
  if bounded_fetch "$toplevel" "$default_branch"; then
    behind=$(cd "$toplevel" 2>/dev/null && git rev-list --count "$default_branch..origin/$default_branch" 2>/dev/null)
    if [ -n "$behind" ] && [ "$behind" -gt 0 ] 2>/dev/null; then
      printf 'checkout %s: %s is %s commits behind origin/%s; pull before you read it\n' \
        "$toplevel" "$default_branch" "$behind" "$default_branch"
    fi
  else
    printf 'checkout %s: cannot check %s against origin, the fetch did not run; freshness unknown\n' \
      "$toplevel" "$default_branch"
  fi
fi

# More than AGENT_WORKTREE_LIMIT `.claude/worktrees/agent-*` worktrees: one notice with the count
# Agent end and the janitor remove finished ones; this says when they
# pile up anyway. One bounded worktree listing, counted with grep. A failed read is reported as
# unknown, never as a count of zero.
AGENT_WORKTREE_LIMIT=50
aw_out=$(mktemp 2>/dev/null)
if [ -n "$aw_out" ]; then
  if bounded_git "$toplevel" "$aw_out" worktree list --porcelain; then
    aw_count=$(grep -c '^worktree .*/\.claude/worktrees/agent-[^/]*$' "$aw_out" 2>/dev/null)
    if [ -n "$aw_count" ] && [ "$aw_count" -gt "$AGENT_WORKTREE_LIMIT" ] 2>/dev/null; then
      printf 'checkout %s: %s agent worktrees exist, more than %s; remove the finished ones\n' \
        "$toplevel" "$aw_count" "$AGENT_WORKTREE_LIMIT"
    fi
  else
    printf 'checkout %s: cannot list the worktrees; the agent worktree count is unknown\n' "$toplevel"
  fi
  rm -f "$aw_out" 2>/dev/null
fi

# The SessionEnd sweep is armed. The record is
# docs/decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md. If the hook goes
# missing from the config, this notice says so. It reads the installed config, never a date
# and never a flag a person must clear, so it stops on its own the day the hook returns.
#
# Three answers, never two, the contract lint/check_unknown_reads_contract.py states. grep
# exits 0 when the hook is present, 1 when the file is readable and the hook is absent, and
# above 1 when the read itself failed. An unreadable config is reported as unknown. It is
# never folded into the armed answer, which would hide the disarm, and never into the
# disarmed answer, which would cry wolf on a machine whose config was simply unreadable.
settings_json="$config_dir/settings.json"
if [ -r "$settings_json" ]; then
  grep -q '"SessionEnd"' "$settings_json" 2>/dev/null
  sessionend_rc=$?
  if [ "$sessionend_rc" -eq 1 ]; then
    printf 'claude-settings: SessionEnd sweep is DISARMED. See docs/decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md\n'
  elif [ "$sessionend_rc" -gt 1 ]; then
    printf 'claude-settings: cannot read %s. SessionEnd sweep state unknown\n' "$settings_json"
  fi
else
  printf 'claude-settings: cannot read %s. SessionEnd sweep state unknown\n' "$settings_json"
fi

exit 0
