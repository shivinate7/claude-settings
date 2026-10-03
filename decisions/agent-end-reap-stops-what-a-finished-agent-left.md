# Agent-end reap stops what a finished agent left

This entry is step 2 of the plan in
decisions/which-start-shapes-outlive-the-agent-on-windows.md (PR #144). That
entry measured which start shapes outlive a subagent on Windows. This entry
records the fix. Governing records:
decisions/unattended-sweep-stops-proven-orphans.md and
decisions/liveness-read-is-platform-specific-and-unreadable-is-not-death.md.

The goal: when a subagent ends, each process it left under its own worktree
stops. Nothing else stops.

## Part 1. The guard refuses the three missed shapes

The `detached-launch` rule in hooks/guard.py now also refuses these shapes:

- A bare `&` job in any segment, not only the last one. The pid must be
  captured with `$!` somewhere in the command, or the rule refuses. A
  leading `&` is PowerShell's call operator, so the rule reads only an `&`
  after the command word.
- `disown` in command position, on any line.
- The same shapes inside the script of `sh -c` or `bash -c`. The rule reads
  that script with the same checks.

The remedy is not changed. It tells the agent to use `run_in_background`.

## Part 2. The sweep takes the deepest checkout

`janitor/sweep.py` `_matching_checkout` now returns the deepest checkout
that holds the cwd. Before, it returned the first one, and that was the
primary checkout.

This change moves one verdict. A listener in an agent worktree is now
judged against the live sessions of that worktree, not those of the
primary checkout. No session record names a subagent. So a running
subagent's worktree reads as "not live". The orphan read still keeps each
server whose parent is alive. A server whose parent died, such as one from
`Start-Process -PassThru`, could then be stopped by the sweep while its agent
still runs.

Owner ruling 2, 2026-09-27: the sweep skips each process whose cwd is under
a `.claude/worktrees/*` checkout. It leaves those folders to
janitor/agent_end_reap.py. `find_swept_listeners` in janitor/sweep.py
applies the skip. The case
`test_the_sweep_leaves_an_orphan_in_an_agent_worktree_to_the_reaper` went
red on a `.bak` copy without the skip. janitor/mutate_sweep.py carries one
mutant for it.

## Part 3. The reaper

`janitor/agent_end_reap.py` is a hook. It reads one hook payload.

- **SubagentStop** gives `agent_id`. The harness names the worktree
  `agent-<agent_id>`. The reaper looks for
  `<primary>/.claude/worktrees/agent-<agent_id>`. It finds the primary
  checkout from the payload `cwd` with `guard.primary_checkout`.
- **WorktreeRemove** names no target. The reaper had a branch for it with
  no agent-id check. Review removed that branch on 2026-09-27, after
  ruling 1. See "Not wired" below.

The target must have the shape `.claude/worktrees/<name>`. It must exist.
It must not be a primary checkout. An agent id must match
`[A-Za-z0-9_-]{1,64}`.

The reaper stops one process only when each read below answers a confirmed
yes:

1. The process cwd is inside the target.
2. No live session has a cwd inside the target
   (`guard.worktree_live_session`).
3. The root of its process tree inside the target is orphaned. The reaper
   climbs from the process to each live parent whose cwd is also inside the
   target. Then it asks `sweep.is_orphan` about the last one. A live parent
   outside the target means keep. A harness or a terminal is such a parent.
4. The current user owns the process.

An unreadable read means keep. The signal goes by pid through
`sweep.send_signal`, once.

Read 3 solves the MSYS stub. The server's parent is a live bash stub, and
the stub's cwd is the worktree. The stub's own parent is dead. So the climb
reaches the stub, and the stub is orphaned. The reaper stops the server and
the stub. A `run_in_background` task of a live agent hangs from a live
`claude.exe` outside the worktree. So the reaper keeps it.

The owner's constraints hold:

- Ownership is judged by the checkout that holds the cwd, never by a name.
- The primary checkout is never a target.
- A worktree that a live session uses is never touched.
- A process that a live parent outside the worktree holds is never touched.

Owner ruling 3, 2026-09-27: this scope is accepted. The reaper stops each
orphaned tree inside an ended agent's worktree, not only listeners.

## Payload log

Each run appends one JSON line to
`${CLAUDE_CONFIG_DIR:-~/.claude}/state/agent-end-payloads.jsonl`. The line
holds the raw payload, the target, and each decision. The hook fields that
the docs leave open get measured from this log. The file keeps the last 200
lines (decisions/guard-trims-from-the-audit.md). The hook always exits 0.

## Not wired: WorktreeRemove

The hooks reference says that WorktreeRemove "Replaces default git
behavior". A hook on that event would stop the harness from removing agent
worktrees. So settings.json wires only SubagentStop. Read from docs, on
2026-09-26, unmeasured.

Owner ruling 1, 2026-09-27: WorktreeRemove stays unwired. SubagentStop
covers the agent end.

## Proof

`janitor/prove_agent_end_reap.py` builds a throwaway repo. It starts one
server in `agent-<A>`, one in `agent-<B>`, and one in the primary checkout.
Each uses the shape measured to outlive the agent. Then it fires a
SubagentStop payload for A.

MEASURED on 2026-09-26, Windows 11, Git Bash, Python 3.14:

| Run | Agent A server | Agent B server | Primary server | Verdict |
|---|---|---|---|---|
| `--old`, only `sweep.py --confirm` | alive | alive | alive | FAIL |
| the reaper, SubagentStop for A | gone | alive | alive | PASS |

In the green run, the reaper stopped two pids in A: the bash stub and the
server. So the stub's cwd is the worktree. That was unmeasured before.
Each run stopped all 6 pids it started, by pid, with 0 left alive.

## Guard measurement

The old guard allowed all 7 new deny cases in hooks/test_guard.py. The new
guard denies them. The suite went red on the old guard, 7 of 594 cases
wrong.

Replayed against 13312 distinct local Bash commands, in 118 sessions: the
first draft refused 6 commands that the old rule allowed. Each one was an
`&` inside a python heredoc body. That `&` is Python code. So the `&` read
now drops each heredoc body first. After that change, 0 commands are newly
refused. The cost: an `&` job inside `bash <<EOF` is not seen.

The deepest-checkout case in janitor/test_sweep.py went red on the old
sweep. hooks/mutate_guard.py and janitor/mutate_sweep.py carry one mutant
for each new rule and for each reaper refusal.

CI on 4864d83 found one survivor: the mutant that drops the `& disown`
clause. The any-segment `&` read also denies `cmd & disown`, so that case
did not prove the clause. The mutant now requires the case
`python3 server.py & disown $!`. The `$!` satisfies the `&` read, so only
the `& disown` clause denies it. MEASURED 2026-09-27: that mutant alone
gives 1 of 596 cases wrong, and that case is the only one. The full
harness ran past its 1200 s suite timeout on this machine, so its local
count is unmeasured.

## What reopens it

- A payload in the log that disagrees with the fields above.
- A subagent worktree name that is not `agent-<agent_id>`.
- A server that a live agent needed, stopped by this reaper or the sweep.
