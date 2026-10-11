# A kill by pid needs a pid this session started

CLAUDE.md says: "Never kill a process you did not start." The guard denied a kill by
name or by pattern. It passed `kill <pid>` for any pid, so a guessed pid, or a pid read
from another agent's server, went through.

## How the guard knows a pid is owned

Measured on macOS: every Bash command and every hook of one session descends from one
process whose command path ends in `claude`. The hook finds that process by walking its
own parent chain. A pid is owned when its own parent chain reaches that process, or when
the process is already dead (`ps` exits 1 with no output). Any other `ps` failure is unknown.
The `claude` process itself is not owned. Another session's process, and the owner's
editor, do not descend from it.

`ps -o ppid=` and `ps -o comm=` give the reads. The chain keeps no list, so nothing can rot.

Owner ruling, 2026-10-10: a pid is also owned when its cwd is inside
`<primary>/.claude/worktrees/agent-<id>`, for an id that this session's subagents hold.
A process a subagent left reads PPID 1 once its parent dies, so the chain test misses it.
Only this session's agent ids count. Another session's agent worktree stays foreign.

## How the guard knows the session's subagent ids

Not built. `write_agent_home` and `read_agent_home` in hooks/guard.py keep
`agent-homes/<agent_id>` under the clone's git common dir. Each record maps an agent id to
its worktree. No record names a session. The payload `session_id` is the same for the
orchestrator and its agents (MEASURED 2026-09-27, macOS, one Explore agent). So
`session_id` cannot tell them apart.

Proposed: on each subagent call, record `agent_id` under the payload `session_id`. This
keeps a list, unlike the pid chain, so it needs a stale-entry rule.

Unmeasured: that every subagent that leaves a process made a call the guard read.
Also unmeasured: that a resumed agent keeps its id, and that two sessions never share a `session_id`.

## The rule

`kill` with a literal pid is denied under rule `machine-wide-kill` when the pid is not owned.
Pids 0, 1, and -1 are always denied, also when the session root is unknown.
`kill $(pgrep ...)`, `kill $(pidof ...)`, and `pgrep ... | xargs kill` name a target by
pattern. They are denied as a kill by name, the same as `pkill`. A pid group (`-123`) is judged by its leader.

## What it does not cover

- `$!`, `$PID`, `%1`, `$(...)`: the guard cannot read them, so they pass. The remedy asks
  for `$!`.
- A lister through a longer pipe (`pgrep x | sort | xargs kill`) passes.
- Process substitution (`kill $(<(pgrep x))`-style forms) passes.
- Pids stored first (`pids=$(pgrep x); kill $pids`) pass.
- A process that reparented to init reads as foreign, unless its cwd is inside one of
  this session's agent worktrees (owner ruling, 2026-10-10). Otherwise stop it through
  the harness.
- When no `claude` ancestor or no `ps` exists (Windows, unmeasured), the guard allows.
  Unknown is not a verdict. `taskkill /PID` and `Stop-Process -Id` pass for the same reason.

## Test hook

`CLAUDE_GUARD_ROOT_PID` (ASCII digits only) replaces the walk. The test suite sets it. A
command cannot set it, because the harness sets the hook's environment. A settings.json
`env` block can.

## Outcome protected

An agent cannot stop another agent's server or the owner's editor by pid. Guard: the
`kill:` cases in `hooks/test_guard.py`, mutations in `hooks/mutate_guard.py`.

The 2026-10-10 ruling widens the owned set to this session's own subagents. It does not
let an agent stop another session's agent or the owner's editor. Proof owed: a case in
`hooks/test_guard.py` where an orphan in this session's agent worktree is allowed, and
one in another session's agent worktree is denied. The allow case must go red on the old
guard before the guard is trusted.
