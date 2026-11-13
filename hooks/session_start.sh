#!/bin/sh
# Prints "checkout <toplevel> on <branch>, <n> dirty files" on start, resume and compaction, after one origin fetch per checkout. Also warns on: core.worktree set in the shared git config; global rules that differ from this checkout; the claude-settings clone off main or behind origin; a default branch or local main behind or off origin; more than 50 agent worktrees; a check that could not run; a waiting page or grant file that differs from main's; a disarmed or unknown SessionEnd sweep. Prints the caution level.
# At a startup start, once the origin refresh ran, it fast-forwards a clean checkout on the default branch that is behind origin and says so; a checkout that is behind but cannot move says why and changes nothing.
# In a git tree it also patches the platform's Stop-hook script once so its unpushed nudge skips a merged branch; it says so when the patch is not applied.
# Outside a git tree or without git, prints only the tier line. Always exits 0, nothing on stderr.

input=$(cat 2>/dev/null)
cwd=$(printf '%s' "$input" | sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
[ -n "$cwd" ] || cwd=$(pwd)
session_id=$(printf '%s' "$input" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
source=$(printf '%s' "$input" | sed -n 's/.*"source"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)

# tier_line: a cloud session (the CLAUDE_CODE_REMOTE read install.sh makes) or a session with a
# CLAUDE_CODE_REMOTE_SESSION_ID tells the session how to find its tier (decision session-tiers). A local
# session with a remote session id also reads its own record, so lane_session_hit (decision
# machine-load-brake) can find its tags. One call runs per run: at the no-git or no-toplevel exit,
# or right after the checkout line, so a cloud session gets it in any folder. The hook cannot read the
# tier itself: get_session and list_sessions are MCP tools only, and a hook never calls the sessions API
# with a token. Cost: at most two env reads, no network, no new process, no timer, no file written.
tier_line() {
  if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || [ -n "${CLAUDE_CODE_REMOTE_SESSION_ID:-}" ]; then
    printf '%s\n' 'session tier: read your own record with get_session (no session_id). A parent_session_id means you are a child of that session, and your cs-build:<tier> tag is your tier. No parent: pick solo, one lane or coordinator from the request. Before you act as coordinator, read every page of list_sessions for a session tagged both cs-build:coordinator and cs-repo:<owner>/<name> for this repo whose session_status is not archived; if one is found, coordinate with it, else proceed. Merge role: this sentence is for a session whose own tag is cs-build:batch-runner, and for no other. Such a session first runs get_session with no argument, in a turn of its own, then runs `~/.claude/bin/merge --role batch-runner`, at session start and after each resume, because a guard checks its tags in that result and a fresh container loses the role file. A lane, the coordinator or any other tier never runs it, and this line is no instruction to it. A coordinator the owner started tags itself cs-build:coordinator with set_session_tags on its own id at start. The coordinator never merges. A solo or one-lane session the owner started, with no parent_session_id, merges its own PR under the repo merge grant or the owner named act. A lane session (tag cs-build:lane, with a parent_session_id) hands its reviewed branch, head and PR to the batch runner (list_sessions, tag cs-build:batch-runner, same repo) and never merges.'
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
  # The watchdog's TERM handler kills its own sleep, so a git call that returns first leaves no sleep behind for
  # the full bound. (jobs -p is empty inside a dash subshell, so the pid is kept in a variable.)
  ( wd_sleep=""
    trap 'kill "$wd_sleep" >/dev/null 2>&1; exit 0' TERM
    sleep "$fetch_timeout" &
    wd_sleep=$!
    wait "$wd_sleep"
    kill "$fetch_pid" >/dev/null 2>&1 ) >/dev/null 2>&1 &
  killer_pid=$!
  wait "$fetch_pid" 2>/dev/null
  fetch_rc=$?
  kill "$killer_pid" >/dev/null 2>&1
  wait "$killer_pid" 2>/dev/null
  return "$fetch_rc"
}

# bounded_fetch <dir>: one quiet, bounded `git fetch` in <dir> that names refs and never prunes or fetches all of
# origin, so its cost does not grow with the remote's branch count (a prune fetch of a 429-branch remote did not finish
# in 20 s; one ref takes well under a second). Returns 0 when the refresh ran, else not. The one home for every
# freshness check below. The first call per checkout runs it; a later call for the same checkout (resolved with pwd -P)
# returns that status again, so a session start refreshes each checkout once, however many checks ask. The caller must
# not run it in $( ), or the memo and fetch_target are lost with the subshell.
# The refs come from the remote, not from local refs: one `git ls-remote --symref origin HEAD refs/heads/main` names
# the remote HEAD's target and says whether main exists. Git fails a whole fetch on a refspec the remote lacks, and a
# local origin/HEAD goes stale when the remote's default is renamed, so a refspec read locally can fail every start.
# The one fetch then names main when the remote lists it, and the target when that is another branch. A remote that
# lists neither is not fetched, since a fetch with no refspec reads the configured wildcard. Only after a good
# ls-remote and a good (or skipped) fetch, a remote with no main has its stale origin/main deleted, a remote-tracking
# ref only. An ls-remote or fetch that fails or is killed counts as not run, deletes nothing and is never retried.
# Bound: each git call has its own CLAUDE_SETTINGS_FETCH_TIMEOUT watchdog, and a failed ls-remote returns before any
# fetch starts, so the worst case is two bounds per checkout (four when the pointer clone is another checkout).
# fetch_target is the remote HEAD's target from this call's ls-remote, and fetch_remote_read is 1 when that read ran;
# a memo hit leaves both as the last run set them.
fetch_memo=""
fetch_reported=""
fetch_target=""
fetch_remote_read=""
bounded_fetch() {
  bf_dir="$1"
  bf_key=$(cd "$bf_dir" 2>/dev/null && pwd -P)
  bf_key="${bf_key:-$bf_dir}"
  bf_hit=""
  while read -r bf_r bf_k; do
    [ "$bf_k" = "$bf_key" ] && bf_hit="$bf_r"
  done <<EOF
$fetch_memo
EOF
  [ -n "$bf_hit" ] && return "$bf_hit"
  fetch_target=""
  fetch_remote_read=""
  bf_rc=1
  bf_ls=$(mktemp 2>/dev/null)
  if [ -n "$bf_ls" ] && bounded_git "$bf_dir" "$bf_ls" ls-remote --symref origin HEAD refs/heads/main; then
    fetch_remote_read=1
    # Lines read: "ref: refs/heads/<t> HEAD" for the target, "<sha> refs/heads/main" when main exists. The pattern HEAD
    # also matches refs that end in /HEAD, so only the exact HEAD field counts.
    bf_has_main=""
    while read -r bf_f1 bf_f2 bf_f3; do
      if [ "$bf_f1" = "ref:" ] && [ "$bf_f3" = HEAD ]; then
        case "$bf_f2" in
          refs/heads/?*) fetch_target="${bf_f2#refs/heads/}" ;;
        esac
      elif [ "$bf_f1" != "ref:" ] && [ "$bf_f2" = refs/heads/main ] && [ -z "$bf_f3" ]; then
        bf_has_main=1
      fi
    done <"$bf_ls"
    set --
    [ -n "$bf_has_main" ] && set -- "+refs/heads/main:refs/remotes/origin/main"
    if [ -n "$fetch_target" ] && [ "$fetch_target" != main ]; then
      set -- "$@" "+refs/heads/$fetch_target:refs/remotes/origin/$fetch_target"
    fi
    bf_rc=0
    if [ "$#" -gt 0 ]; then
      bounded_git "$bf_dir" /dev/null fetch --quiet --no-tags origin "$@"
      bf_rc=$?
    fi
    if [ "$bf_rc" -eq 0 ] && [ -z "$bf_has_main" ]; then
      (cd "$bf_dir" 2>/dev/null && git update-ref -d refs/remotes/origin/main >/dev/null 2>&1)
    fi
  fi
  [ -n "$bf_ls" ] && rm -f "$bf_ls" 2>/dev/null
  fetch_memo="$fetch_memo
$bf_rc $bf_key"
  return "$bf_rc"
}

# fetch_mark_reported <dir>, fetch_was_reported <dir>: a check that prints its own "the fetch did not run" line
# marks the checkout, so the session start prints one such line per checkout, not two.
fetch_mark_reported() {
  fr_key=$(cd "$1" 2>/dev/null && pwd -P)
  fetch_reported="$fetch_reported
${fr_key:-$1}"
}
fetch_was_reported() {
  fr_key=$(cd "$1" 2>/dev/null && pwd -P)
  case "
$fetch_reported
" in
    *"
${fr_key:-$1}
"*) return 0 ;;
  esac
  return 1
}

toplevel=$(cd "$cwd" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)
[ -n "$toplevel" ] || { tier_line; exit 0; }

branch=$(cd "$cwd" 2>/dev/null && git rev-parse --abbrev-ref HEAD 2>/dev/null)
[ "$branch" = "HEAD" ] && branch="detached"

n=$(cd "$cwd" 2>/dev/null && git status --porcelain 2>/dev/null | wc -l | tr -d '[:space:]')

printf 'checkout %s on %s, %s dirty files\n' "$toplevel" "$branch" "$n"
tier_line

# Local origin/HEAD's target, empty when unset. The default-branch check below tests the checkout against it. The
# grants compare reads gm_default instead: the remote HEAD's target when the refresh read the remote, since that is
# the branch the fetch refreshed and a local origin/HEAD goes stale when the remote's default is renamed; else this.
default_branch=$(cd "$toplevel" 2>/dev/null && git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null)
default_branch="${default_branch#origin/}"

# Step grants-read-from-main: a session cites the standing grants from origin/main, never from its own checkout,
# because a stale checkout once led a coordinator to cite acts the owner never gave. A checkout with an origin
# remote is refreshed first with bounded_fetch (one fetch of main and the remote HEAD's target, no prune, on any
# branch or a detached HEAD), so the compare reads a current origin/main, not a stale one. The block runs right after
# the tier line, before every slow step (the worktree listing, the caution call): a hook the platform kills at its
# timeout loses all later output, and these lines are the ones a session must not lose. A refresh that fails or times out prints one
# "did not run" line (the later freshness checks then print none of their own for this checkout) and marks each grant
# line as read from an unrefreshed ref. No origin remote: no fetch and no refresh line; the compare below still
# runs, so a remote-less repo with a grant file at HEAD prints the unknown-grant line. The compare is the HEAD blob of each
# grant file (CLAUDE.md, .claude/CLAUDE.md) in the session's toplevel against the blob at origin/main, or at
# the default branch ($gm_default) when origin/main is absent. A file that differs, or sits on one
# side only, prints one line with the ref tip's short sha and the git show command that reads the ref's copy. When
# neither ref reads and a grant file exists at HEAD, one unknown line prints. Only committed blobs are compared,
# so an uncommitted edit prints nothing. Local main is counted against origin/main with one rev-list and never
# moved; the line prints only when they differ, and not when the default-branch check above already said behind.
# Cost: once per SessionStart event (start, resume or compaction), never per prompt (the hook is wired to SessionStart only): one git ls-remote and
# at most one git fetch of this checkout (shared with the later freshness checks, so at most one each per checkout),
# whose own writes are refs, objects and FETCH_HEAD, plus one git update-ref when the remote has no main; one temp
# file for the ls-remote answer, removed in the same call; one git remote read, one git cat-file --batch-check and one git rev-list, plus, only
# when local main differs, one git config read and, when the pointer clone printed behind, two git rev-parse
# reads, all local. The ls-remote and the fetch are each bounded by a watchdog (bounded_git): a short-lived subshell and
# a sleep of at most CLAUDE_SETTINGS_FETCH_TIMEOUT seconds; the sleep is killed when git returns first. When the bound
# hits, the kill reaches only the subshell that runs git, so on bash the git child may finish after the hook
# exits. It is bounded by git's own run (an ls-remote, or a fetch of one or two refs) and is never a daemon. No other
# timer. The hook itself keeps no file; that late git writes only its own refs, objects and FETCH_HEAD.
gm_unref=""
gm_differs=""
gm_remote_read=""
gm_default="$default_branch"
if (cd "$toplevel" 2>/dev/null && git remote 2>/dev/null | grep -qx origin); then
  bounded_fetch "$toplevel"
  gm_fetch_rc=$?
  if [ -n "$fetch_remote_read" ]; then
    gm_remote_read=1
    gm_default="$fetch_target"
  fi
  if [ "$gm_fetch_rc" -ne 0 ]; then
    gm_unref=1
    if ! fetch_was_reported "$toplevel"; then
      printf 'checkout %s: the origin fetch did not run, so origin refs may be stale; freshness unknown\n' "$toplevel"
      fetch_mark_reported "$toplevel"
    fi
  fi
fi
gm_out=$( {
  printf '%s\n' 'HEAD:CLAUDE.md' 'HEAD:.claude/CLAUDE.md' 'origin/main' 'origin/main:CLAUDE.md' 'origin/main:.claude/CLAUDE.md'
  if [ -n "$gm_default" ] && [ "$gm_default" != "main" ]; then
    printf '%s\n' "origin/$gm_default" "origin/$gm_default:CLAUDE.md" "origin/$gm_default:.claude/CLAUDE.md"
  fi
} | { cd "$toplevel" 2>/dev/null && git cat-file --batch-check='%(objectname) %(objecttype)' 2>/dev/null; } )
# gm_pick <n> <type>: the object name on line n of the answer when that line names an object of <type>, else nothing.
gm_pick() {
  printf '%s\n' "$gm_out" | sed -n "${1}p" | awk -v t="$2" 'NF == 2 && $2 == t { print $1 }'
}
if [ -n "$gm_out" ]; then
  gm_head1=$(gm_pick 1 blob)
  gm_head2=$(gm_pick 2 blob)
  gm_ref=""
  gm_tip=$(gm_pick 3 commit)
  if [ -n "$gm_tip" ]; then
    gm_ref="origin/main"
    gm_ref1=$(gm_pick 4 blob)
    gm_ref2=$(gm_pick 5 blob)
  elif [ -n "$gm_default" ] && [ "$gm_default" != "main" ]; then
    gm_tip=$(gm_pick 6 commit)
    if [ -n "$gm_tip" ]; then
      gm_ref="origin/$gm_default"
      gm_ref1=$(gm_pick 7 blob)
      gm_ref2=$(gm_pick 8 blob)
    fi
  fi
  if [ -n "$gm_ref" ]; then
    gm_note=""
    [ -n "$gm_unref" ] && gm_note="; $gm_ref is unrefreshed"
    if [ "$gm_head1" != "$gm_ref1" ]; then
      gm_differs=1
      printf 'checkout %s: CLAUDE.md differs from %s at %.12s; read the standing grants with git show %s:CLAUDE.md%s\n' \
        "$toplevel" "$gm_ref" "$gm_tip" "$gm_ref" "$gm_note"
    fi
    if [ "$gm_head2" != "$gm_ref2" ]; then
      gm_differs=1
      printf 'checkout %s: .claude/CLAUDE.md differs from %s at %.12s; read the standing grants with git show %s:.claude/CLAUDE.md%s\n' \
        "$toplevel" "$gm_ref" "$gm_tip" "$gm_ref" "$gm_note"
    fi
  elif [ -n "$gm_head1" ] || [ -n "$gm_head2" ]; then
    printf 'checkout %s: standing grant check unknown, neither origin/main nor origin/HEAD could be read\n' "$toplevel"
  fi
fi

# Step fast-forward-clean-start: a session that starts on a stale checkout once read old files as current. At a
# startup start only (a resume or compact start keeps what the session already read), when the refresh above ran,
# a checkout that is behind origin/<default> and clean moves to it with `git merge --ff-only`, which can only move
# forward and never rewrites a commit. Clean: no uncommitted or untracked file (the dirty count read at the top), no
# merge, cherry-pick, revert or rebase in progress, no commit ahead of origin, HEAD on the default branch. A checkout
# that is behind but not clean is left as it is and says why, one line, so the session knows its files are stale. An
# agent worktree is another session's, so it is never moved. The live pin is skipped: merge-reinstalls-from-main owns it.
# Up to date, or ahead only: no line (the later ahead check covers that). The default is $gm_default, the branch the
# refresh fetched, so no second fetch runs. A merge that fails says so and leaves git's own state.
# Cost: one git rev-list per startup start, plus one git rev-parse for the in-progress files and one git diff for the
# added paths when the checkout is behind, plus one git ls-files per added path with something on disk in its way, plus (only when it moves) two git rev-parse and one git merge. All local, no network, no file written by the
# hook; the merge writes the working tree, index and HEAD of this checkout only.
ff_done=""
if [ "$source" = startup ] && [ "${gm_fetch_rc:-1}" -eq 0 ] 2>/dev/null && [ -n "$gm_default" ]; then
  ff_base=""
  case "$toplevel" in
    *-live-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ff_base="${toplevel%-live-*}" ;;
    *-live) ff_base="${toplevel%-live}" ;;
  esac
  if [ -z "$ff_base" ] || [ ! -f "$ff_base/merge/install_from_main.sh" ]; then
    ff_counts=$(cd "$toplevel" 2>/dev/null && git rev-list --left-right --count "HEAD...origin/$gm_default" 2>/dev/null)
    ff_ahead=""
    ff_behind=""
    read -r ff_ahead ff_behind <<EOF
$ff_counts
EOF
    if [ -n "$ff_behind" ] && [ "$ff_behind" -gt 0 ] 2>/dev/null; then
      ff_reason=""
      case "$toplevel" in
        */.claude/worktrees/agent-*) ff_reason="another agent's worktree" ;;
      esac
      if [ -z "$ff_reason" ]; then
        if [ "$branch" = "detached" ]; then
          ff_reason="detached HEAD"
        elif [ "$branch" != "$gm_default" ]; then
          ff_reason="not on $gm_default"
        else
          ff_prog=$(cd "$toplevel" 2>/dev/null && git rev-parse --git-path MERGE_HEAD --git-path CHERRY_PICK_HEAD \
            --git-path REVERT_HEAD --git-path rebase-merge --git-path rebase-apply 2>/dev/null \
            | while read -r ff_p; do [ -e "$ff_p" ] && { echo 1; break; }; done)
          if [ -n "$ff_prog" ]; then
            ff_reason="merge or rebase in progress"
          elif [ "$n" -gt 0 ] 2>/dev/null; then
            ff_reason="uncommitted changes"
          elif [ "$ff_ahead" -gt 0 ] 2>/dev/null; then
            ff_reason="diverged"
          else
            # Something untracked on disk at a path the move adds, or a file or symlink at one of its parents, is an
            # ignored one (a non-ignored one made the tree dirty above): git would overwrite it or write through it, so
            # the move does not run. A tracked one is git's own to replace, and a parent directory holds the new file
            # without harm. --no-renames lists a rename's target as added, so it is checked too.
            # A tracked directory that origin replaces with a file goes with whatever ignored files it holds, so that
            # case holds too. Literal pathspecs, so a name holding * or ? cannot match some other tracked path. No
            # comment, case or quote sits inside the substitution below: bash 3.2 (macOS sh) mis-parses those there.
            ff_hit=$(cd "$toplevel" 2>/dev/null && git diff -z --no-renames --name-only --diff-filter=A HEAD "origin/$gm_default" 2>/dev/null \
              | tr '\0' '\n' | while IFS= read -r ff_p; do
                  ff_in=""
                  if [ -e "$ff_p" ] || [ -L "$ff_p" ]; then ff_in="$ff_p"; fi
                  ff_d="$ff_p"
                  while [ -z "$ff_in" ]; do
                    [ "${ff_d%/*}" != "$ff_d" ] || break
                    ff_d="${ff_d%/*}"
                    if [ -L "$ff_d" ] || { [ -e "$ff_d" ] && [ ! -d "$ff_d" ]; }; then ff_in="$ff_d"; fi
                  done
                  if [ -n "$ff_in" ]; then
                    if [ -z "$(git --literal-pathspecs ls-files -- "$ff_in" 2>/dev/null)" ]; then echo 1; break; fi
                    if [ -d "$ff_in" ] && [ ! -L "$ff_in" ] \
                      && [ -n "$(git --literal-pathspecs ls-files -z -o -i --exclude-standard -- "$ff_in" 2>/dev/null | tr '\0' '\n')" ]; then echo 1; break; fi
                  fi
                done)
            [ -n "$ff_hit" ] && ff_reason="an ignored file is in the way"
          fi
        fi
      fi
      if [ -n "$ff_reason" ]; then
        printf 'checkout %s: not fast-forwarded, %s\n' "$toplevel" "$ff_reason"
      else
        ff_old=$(cd "$toplevel" 2>/dev/null && git rev-parse --short=12 HEAD 2>/dev/null)
        ff_new=$(cd "$toplevel" 2>/dev/null && git rev-parse --short=12 "origin/$gm_default" 2>/dev/null)
        if (cd "$toplevel" 2>/dev/null && git merge --ff-only --quiet "origin/$gm_default" >/dev/null 2>&1); then
          ff_note=""
          # The grant lines printed above compared the old files; after the move they match origin's.
          [ -n "$gm_differs" ] && ff_note="; the grant lines above are now current"
          printf 'checkout %s: fast-forwarded %s %s -> %s, %s commits%s\n' "$toplevel" "$branch" "$ff_old" "$ff_new" "$ff_behind" "$ff_note"
          ff_done=1
        else
          printf 'checkout %s: not fast-forwarded, the merge failed\n' "$toplevel"
        fi
      fi
    fi
  fi
fi

# Decision merge-reinstalls-from-main, ruling 1: no work runs in the live pin. A cwd whose toplevel is the
# pin says so, and names the clone to cd to. Same test as live_pin_clone in install.sh, repeated here
# because sh cannot source install.sh. The pin is <clone>-live, or <clone>-live-<12 hex>, as a linked worktree
# of a claude-settings clone: the clone holds merge/install_from_main.sh, as in hooks/guard_frozen.py.
# The line prints git's own path forms ($toplevel, the listing's first entry), as the checkout line does; pwd -P forms are for the comparisons only.
# This one bounded worktree listing (wl_out) also feeds the agent worktree count below, which removes it.
wl_out=$(mktemp 2>/dev/null)
wl_ok=0
if [ -n "$wl_out" ]; then
  bounded_git "$toplevel" "$wl_out" worktree list --porcelain && wl_ok=1
  if [ "$wl_ok" = 1 ]; then
    lp_clone=$(sed -n '1s/^worktree //p' "$wl_out" 2>/dev/null)
    lp_top=$(cd "$toplevel" 2>/dev/null && pwd -P)
    lp_base=$(cd "$lp_clone" 2>/dev/null && pwd -P)
    if [ -n "$lp_top" ] && [ -n "$lp_base" ] && [ "$lp_top" != "$lp_base" ] \
       && [ -f "$lp_base/merge/install_from_main.sh" ]; then
      lp_is_pin=0
      case "$lp_top" in
        "$lp_base"-live-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) lp_is_pin=1 ;;
        *) [ "$lp_top" = "$(cd "$lp_base-live" 2>/dev/null && pwd -P)" ] && lp_is_pin=1 ;;
      esac
      if [ "$lp_is_pin" = 1 ]; then
        printf 'checkout %s is the live pin: no work runs in it (decision merge-reinstalls-from-main). cd to the clone %s before you change anything.\n' "$toplevel" "$lp_clone"
      fi
    fi
  fi
fi

# Rule session-home: a resumed session whose recorded worktree folder is gone says so once, before it
# writes. The record is `<primary>/.git/session-homes/<session_id>` (hooks/guard.py writes it). The
# primary comes from the toplevel's path shape, so this adds no git call. The line never names the path.
if [ "$source" = "resume" ]; then
  case "$session_id" in
    ""|*[!A-Za-z0-9._-]*) ;;
    *)
      sh_primary="$toplevel"
      case "$toplevel" in
        */.claude/worktrees/*) sh_primary="${toplevel%%/.claude/worktrees/*}" ;;
      esac
      sh_record="$sh_primary/.git/session-homes/$session_id"
      if [ -d "$sh_primary/.git" ] && [ -f "$sh_record" ]; then
        sh_home=$(cat "$sh_record" 2>/dev/null)
        if [ -n "$sh_home" ] && [ ! -d "$sh_home" ]; then
          printf '%s\n' "session-home: this session's worktree is gone. Call the EnterWorktree tool before you change any file; the guard refuses a write into the primary checkout until then."
        fi
      fi
      ;;
  esac
fi

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
# pointer names, for example an agent's worktree. In any other repo, the pointer's CLAUDE.md and
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
# A checkout detached at local main's commit or at origin/main's tip counts as on main (the pointer lags local
# main when a fetch moved origin/main first); detached anywhere else is off main.
if [ -n "$d" ] && [ -e "$d/.git" ]; then
  pointer_branch=$(cd "$d" 2>/dev/null && git rev-parse --abbrev-ref HEAD 2>/dev/null)
  if [ "$pointer_branch" = "HEAD" ]; then
    pin_head=$(cd "$d" 2>/dev/null && git rev-parse HEAD 2>/dev/null)
    main_head=$(cd "$d" 2>/dev/null && git rev-parse --verify -q refs/heads/main 2>/dev/null)
    origin_head=$(cd "$d" 2>/dev/null && git rev-parse --verify -q refs/remotes/origin/main 2>/dev/null)
    if [ -n "$pin_head" ] && { [ "$pin_head" = "$main_head" ] || [ "$pin_head" = "$origin_head" ]; }; then
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
    if bounded_fetch "$d"; then
      behind=$(cd "$d" 2>/dev/null && git rev-list --count main..origin/main 2>/dev/null)
      if [ -n "$behind" ] && [ "$behind" -gt 0 ] 2>/dev/null; then
        printf 'claude-settings: %s is %s commits behind origin/main; global rules and hooks are stale\n' \
          "$d" "$behind"
        ptr_behind_printed=1
      fi
    else
      if ! fetch_was_reported "$d"; then
        printf 'claude-settings: cannot check %s against origin/main, the fetch did not run; freshness unknown\n' \
          "$d"
        fetch_mark_reported "$d"
      fi
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
# the fetch never moves a local branch (it may write FETCH_HEAD and remote-tracking refs). An unknown default branch means no line.
# When the refresh read the remote and its HEAD names another branch, the local default is stale and was not fetched,
# so a count against it could read 0 behind on a stale ref: no line then.
if [ -n "$default_branch" ] && [ "$branch" = "$default_branch" ] && [ -z "$ff_done" ] \
   && { [ -z "$gm_remote_read" ] || [ "$gm_default" = "$default_branch" ]; } \
   && { [ -z "$d" ] || [ "$(cd "$toplevel" 2>/dev/null && pwd -P)" != "$(cd "$d" 2>/dev/null && pwd -P)" ]; }; then
  if bounded_fetch "$toplevel"; then
    behind=$(cd "$toplevel" 2>/dev/null && git rev-list --count "$default_branch..origin/$default_branch" 2>/dev/null)
    if [ -n "$behind" ] && [ "$behind" -gt 0 ] 2>/dev/null; then
      printf 'checkout %s: %s is %s commits behind origin/%s; pull before you read it\n' \
        "$toplevel" "$default_branch" "$behind" "$default_branch"
      dflt_behind_printed=1
    fi
  else
    if ! fetch_was_reported "$toplevel"; then
      printf 'checkout %s: cannot check %s against origin, the fetch did not run; freshness unknown\n' \
        "$toplevel" "$default_branch"
      fetch_mark_reported "$toplevel"
    fi
  fi
fi

# More than AGENT_WORKTREE_LIMIT `.claude/worktrees/agent-*` worktrees: one notice with the count
# Agent end and the janitor remove finished ones; this says when they
# pile up anyway. Counted with grep from the one worktree listing read above (wl_out). A failed read is
# reported as unknown, never as a count of zero.
AGENT_WORKTREE_LIMIT=50
if [ -n "$wl_out" ]; then
  if [ "$wl_ok" = 1 ]; then
    aw_count=$(grep -c '^worktree .*/\.claude/worktrees/agent-[^/]*$' "$wl_out" 2>/dev/null)
    if [ -n "$aw_count" ] && [ "$aw_count" -gt "$AGENT_WORKTREE_LIMIT" ] 2>/dev/null; then
      printf 'checkout %s: %s agent worktrees exist, more than %s; remove the finished ones\n' \
        "$toplevel" "$aw_count" "$AGENT_WORKTREE_LIMIT"
    fi
  else
    printf 'checkout %s: cannot list the worktrees; the agent worktree count is unknown\n' "$toplevel"
  fi
  rm -f "$wl_out" 2>/dev/null
fi

# Rule page-stale: a repo whose extras name a waiting page prints one line when the page was last published
# from a version other than main's page.html. The stamp an allowed publish wrote
# (<git common dir>/waiting-page-built) holds main's blob sha at that publish; skills/waiting-page/stale_pages.py
# --session-line compares it with origin/main of the claude-settings clone ($d) and prints the line, or nothing
# (no stamp, or main unreadable, is silent). The grep is only a cheap filter on the extras file that
# lint/layout.json names; layout.waiting_page, inside the python start, decides. Cost: in a repo with a page, one
# python start and one read-only git process; in any other repo, one grep. No fetch, no file written, no timer.
wp_extras="$toplevel/.claude/layout-extras.json"
if [ -f "$wp_extras" ] && grep -q '"waiting-page"' "$wp_extras" 2>/dev/null && command -v python3 >/dev/null 2>&1; then
  wp_script="$(cd "$(dirname "$0")" 2>/dev/null && pwd)/../skills/waiting-page/stale_pages.py"
  [ -f "$wp_script" ] || wp_script="$config_dir/skills/waiting-page/stale_pages.py"
  if [ -f "$wp_script" ]; then
    if [ -n "$d" ]; then
      wp_line=$(python3 "$wp_script" --session-line "$toplevel" --main-checkout "$d" 2>/dev/null)
    else
      wp_line=$(python3 "$wp_script" --session-line "$toplevel" 2>/dev/null)
    fi
    [ -n "$wp_line" ] && printf '%s\n' "$wp_line"
  fi
fi

# The owner's rulings that main has not yet taken in (the ruled store, decision ruled-store-one-home): lint/ruled_store.py
# --session-line prints one header, up to five entry lines and a command line, or nothing. It reads origin/roadmap and
# origin/main of the claude-settings clone ($d), else of this checkout, as the fetches above left them: no fetch of its
# own. Any failure is silent and never changes the exit. Cost: once per SessionStart event, one python start and two
# read-only git processes (ls-tree, cat-file --batch), plus a third cat-file when an open entry names the text it lands
# in; no file written, no timer, no process kept.
if command -v python3 >/dev/null 2>&1; then
  rs_script="$(cd "$(dirname "$0")" 2>/dev/null && pwd)/../lint/ruled_store.py"
  [ -f "$rs_script" ] || rs_script="$config_dir/lint/ruled_store.py"
  if [ -f "$rs_script" ]; then
    rs_repo="$toplevel"
    [ -n "$d" ] && [ -e "$d/.git" ] && rs_repo="$d"
    rs_lines=$(python3 "$rs_script" --session-line "$rs_repo" 2>/dev/null)
    [ -n "$rs_lines" ] && printf '%s\n' "$rs_lines"
  fi
fi

# Local main against origin/main: `main...origin/main` counts local-only commits (ahead) on the left and
# origin-only commits (behind) on the right. Silent when either ref is absent or the two are equal. Also silent
# when a behind line for this repo's main already printed (the default-branch check, or the pointer check when
# the pointer clone and this checkout share a git common dir, which a live pin does), and on a clone install.sh
# made (claude-settings.cloudMirror), which the cloud resume refreshes.
lm_skip=""
[ -n "$dflt_behind_printed" ] && lm_skip=1
if [ -z "$lm_skip" ] && [ -n "$ptr_behind_printed" ]; then
  lm_ptr_common=$(cd "$d" 2>/dev/null && cd "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null && pwd -P)
  lm_top_common=$(cd "$toplevel" 2>/dev/null && cd "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null && pwd -P)
  [ -n "$lm_ptr_common" ] && [ "$lm_ptr_common" = "$lm_top_common" ] && lm_skip=1
fi
if [ -z "$lm_skip" ]; then
  lm_counts=$(cd "$toplevel" 2>/dev/null && git rev-list --left-right --count refs/heads/main...refs/remotes/origin/main 2>/dev/null)
  lm_ahead=${lm_counts%%[[:space:]]*}
  lm_behind=${lm_counts##*[[:space:]]}
  lm_mirror=""
  if [ -n "$lm_counts" ] && { [ "${lm_ahead:-0}" -gt 0 ] || [ "${lm_behind:-0}" -gt 0 ]; } 2>/dev/null; then
    lm_mirror=$(cd "$toplevel" 2>/dev/null && git config --get claude-settings.cloudMirror 2>/dev/null)
  fi
  if [ -n "$lm_counts" ] && [ "$lm_mirror" != "true" ] \
     && { [ "${lm_ahead:-0}" -gt 0 ] || [ "${lm_behind:-0}" -gt 0 ]; } 2>/dev/null; then
    lm_line="checkout $toplevel: local main is $lm_behind commit"
    [ "$lm_behind" = 1 ] || lm_line="${lm_line}s"
    lm_line="$lm_line behind origin/main"
    if [ "$lm_ahead" -gt 0 ]; then
      lm_line="$lm_line and $lm_ahead commit"
      [ "$lm_ahead" = 1 ] || lm_line="${lm_line}s"
      lm_line="$lm_line ahead"
    fi
    printf '%s\n' "$lm_line"
  fi
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

# Patch the platform's Stop-hook script ($config_dir/stop-hook-git-check.sh, written by the platform before this
# hook runs) so its unpushed-commits nudge skips a branch whose head origin/main already holds. Granted by the
# owner, page item 464 b, for this one patch (decision lanes-start-in-tool-worktrees).
# The nudge recreated a deleted branch as a copy of main. A squash-merged branch is not an ancestor of origin/main,
# so it is not skipped; this repo merges with merge commits.
# Cost: one file read per session start, one write only when patching (a temp file in the same folder, then mv),
# no process kept, no timer. A missing file is silent. A file whose anchor line is missing or doubled stays
# byte-identical, and one line says so.
stop_hook="$config_dir/stop-hook-git-check.sh"
if [ -f "$stop_hook" ] && [ -w "$stop_hook" ] && [ -w "$config_dir" ] \
  && ! grep -qF '# claude-settings: skip-merged' "$stop_hook" 2>/dev/null; then
  # SC2016: the anchor holds literal dollar signs from the platform's text.
  # shellcheck disable=SC2016
  stop_anchor='  unpushed=$(git rev-list "$upstream..HEAD" --count 2>/dev/null) || unpushed=0'
  stop_anchor_count=$(grep -cxF -- "$stop_anchor" "$stop_hook" 2>/dev/null)
  if [ "$stop_anchor_count" = 1 ]; then
    stop_block='  # claude-settings: skip-merged
  # Skip a branch whose head origin/main already holds (owner, page item 464 b, 2026-11-09 13:09 CST):
  # the nudge recreated a deleted branch as a copy of main.
  git merge-base --is-ancestor HEAD origin/main 2>/dev/null && unpushed=0'
    stop_tmp=$(mktemp "$config_dir/.stop-hook-git-check.XXXXXX" 2>/dev/null)
    if [ -n "$stop_tmp" ]; then
      # cp -p carries the mode; the redirect keeps it while the contents are replaced.
      if cp -p "$stop_hook" "$stop_tmp" 2>/dev/null \
        && STOP_ANCHOR="$stop_anchor" STOP_BLOCK="$stop_block" \
          awk '$0 == ENVIRON["STOP_ANCHOR"] { print; print ENVIRON["STOP_BLOCK"]; next } { print }' "$stop_hook" >"$stop_tmp" 2>/dev/null \
        && mv -f "$stop_tmp" "$stop_hook" 2>/dev/null; then
        :
      else
        rm -f "$stop_tmp" 2>/dev/null
      fi
    fi
  else
    printf 'claude-settings: Stop-hook patch not applied, the platform script text changed (%s)\n' "$stop_hook"
  fi
fi

exit 0
