# Agent-end reap stops what a finished agent left

Kind: process
Home: janitor/agent_end_reap.py

Governing record: `unattended-sweep-stops-proven-orphans` (a sweep stops only proven orphans).

## The ruling

The goal: when an agent ends, each process it left under its own worktree stops. Nothing else
stops. When the worktree is removed is in `when-a-worktree-may-be-removed`.

### The sweep takes the deepest checkout

`janitor/sweep.py` `_matching_checkout` returns the deepest checkout that holds the cwd, not the
primary checkout. Reason: no session record names an agent, so a running agent's worktree reads as
"not live".

Owner ruling, 2026-09-27: the sweep skips each process whose cwd is under a `.claude/worktrees/*`
checkout. It leaves those folders to janitor/agent_end_reap.py.

### The reaper

`janitor/agent_end_reap.py` runs on SubagentStop only. The payload `agent_id` gives the target,
`<primary>/.claude/worktrees/agent-<agent_id>`. The target must exist, have the shape
`.claude/worktrees/<name>`, and not be a primary checkout.

The reaper stops one process only when each read below answers a confirmed yes:

1. The process cwd is inside the target, read in one batch.
2. No live session has a cwd inside the target (`guard.worktree_live_session`).
3. The root of its process tree inside the target is orphaned. The reaper climbs from the
   process to each live parent whose cwd is also inside the target. Then it asks
   `sweep.is_orphan` about the last one. A live parent outside the target means keep. A
   harness or a terminal is such a parent. Read 3 applies in the ending agent's own worktree too.
4. The current user owns the process.

An unreadable read means keep. The signal goes by pid through `sweep.send_signal`, once. Ownership is
judged by the checkout that holds the cwd, never by a name.

Reason for read 3: an orphaned shell stub has a dead parent, so the reaper stops the server and the stub.
On Windows, `cmd &` then another line in one foreground Bash call outlives the agent. Its parent is a live MSYS bash stub, and the tool shell above the stub is dead. `sweep.is_orphan` alone reads the live stub and keeps the server forever, so the reaper climbs to the root of the tree inside the target.
A `run_in_background` task of a live agent hangs from a live host outside the worktree, so the reaper
keeps it. The agent's own shells have the live host as parent, so they keep the tree (`when-a-worktree-may-be-removed`).

Owner ruling, 2026-09-27: the reaper stops each orphaned tree inside an ended agent's worktree, not
only listeners. The reaper targets only the ending agent's tree.

Owner ruling, 2026-10-10: the guard's ownership change changes the guard's kill rule only. The reaper's
reads stay as above (`a-kill-by-pid-needs-an-owned-pid`).

Owner ruling, 2026-10-10: the reap reads every process's cwd in one batch call
(`sweep._read_all_cwds_macos`). A failed or empty read returns None, which means keep. Reason: a reap
that hit the 60 s hook cap sent no signal and left a server running. The batch timeout stays below the
hook cap.

Owner ruling, 2026-10-26: scratchpad orphans are reaped at session end by `janitor/session_end_sweep.py`, not at agent end. Reason: the session and its agents share one scratchpad and no agent tag exists, so an agent-end reap would stop live servers of the session or of a sibling lane. The session-end reap stops a process only when its parent is init, its exec environment holds exactly `CLAUDE_CODE_SESSION_ID=<payload session_id>`, and its cwd is inside the realpath of the payload `scratchpad_dir`. No `scratchpad_dir` stops nothing. A failed read keeps. `janitor/agent_end_reap.py` stays as above.

The payload log is written under a lock file. Measured on b0c87cb (PR 322 review): 13 of 120 rows were lost at 3 writers with a shared temp name and no lock.
