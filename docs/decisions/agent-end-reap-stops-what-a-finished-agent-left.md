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

The sweep skips each process whose cwd is under a `.claude/worktrees/*` checkout. This reaper owns
those folders (owner ruling, 2026-09-27).

### The reaper

`janitor/agent_end_reap.py` runs on SubagentStop only. The payload `agent_id` gives the target,
`<primary>/.claude/worktrees/agent-<agent_id>`. The target must exist, have the shape
`.claude/worktrees/<name>`, and not be a primary checkout.

The reaper stops one process only when each read below answers a confirmed yes:

1. The process cwd is inside the target, read in one batch.
2. No live session has a cwd inside the target (`git_reads.worktree_live_session`).
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
keeps it. The agent's own shells have the live host as parent, so read 3 keeps them. A later agent end stops a background job's processes by the marker rule below; a foreground call's servers stay.

The reaper stops each orphaned tree inside the ended agent's worktree, not only listeners. That stop targets
only that tree (owner ruling, 2026-09-27).

### A finished agent's processes, by marker

At a later agent end, the reaper stops the processes inside a finished agent's host-locked tree when each is the agent's own by its marker (owner ruling, 2026-10-15 19:43 CDT; coordinator picks, 2026-11-07 14:43 and 15:05 CST; coordinator 16:14 CST, option 1). The stall-watch hook puts `export CLAUDE_AGENT_ID=<agent_id>` in front of the wrapper of each background agent Bash call, so each process the job execs holds the agent marker in its exec-time environment. A foreground call is not rewritten, because Claude Code checks permission rules on a hook's rewritten input; its processes are unmarked and keep the tree. `sweep.host_child_stops` stops a pid that holds the marker equal to the 17-hex id in the tree's basename. It also stops a pid that holds none when a marked pid in the tree descends from it (the job's `( )` subshell is a fork, so unmarked). The parent of a left-behind process is any pid: an orphan lands on PID 1, not the host. Another id, an unmarked pid no marked pid descends from, a basename that is not `agent-<17 hex>`, or a failed read keeps the tree and stops nothing. The tree rules (finish proof, unlock first, settle, relock on a survivor) are in `when-a-worktree-may-be-removed`, "A finished agent's tree".

Measured facts (Linux): an orphaned server lands on PID 1, not on the host. Each Bash call is its own session leader, so a process group or session id cannot span calls. An export reaches exec'd children and not the call's own bash. The job's `( )` subshell is a fork, so unmarked; its exec'd children are marked. The harness sets no agent marker. The macOS read of the marker is unmeasured. Windows reads no marker, so its processes are unmarked and keep the tree.

Cost, per finished tree with a process inside: one environment read per pid listed inside, and one `ps` read per ancestor climbed from each marked pid (none for an unmarked pid; macOS adds one `lsof` batch for the cwds, in the enumeration). The hook also reads `ps` once per ancestor of its own (`_own_chain_pids`, the protected set). No timer, no file. A test pins the `ps` count.

The guard's kill rule is separate from the reaper's reads. The guard's ownership change
(`a-kill-by-pid-needs-an-owned-pid`) did not change them (owner ruling, 2026-10-10).

The reap reads every process's cwd in one batch call (`sweep._read_all_cwds_macos`). A failed or empty
read returns None, which means keep. The batch timeout stays below the hook cap (owner ruling,
2026-10-10). Reason: a reap that hit the 60 s hook cap sent no signal and left a server running.

Scratchpad orphans are reaped at session end by `janitor/session_end_sweep.py`, not at agent end (owner ruling, 2026-10-26). Reason: the session and its agents share one scratchpad, and no agent marker existed then. An agent-end reap would stop live servers of the session or of a sibling lane. The session-end reap stops a process only when its parent is init, its exec environment holds exactly `CLAUDE_CODE_SESSION_ID=<payload session_id>`, and its cwd is inside the realpath of the payload `scratchpad_dir`. No `scratchpad_dir` stops nothing. A failed read keeps. The agent-end reap keeps the reads above and covers the ending agent's tree only.

## The payload log

The payload log is `state/agent-end-payloads.jsonl` under the config dir. Each agent end writes a `started` row, then a `done` row. The `done` row replaces the `started` row when that row is still the last line. Writes take the lock file `<log>.lock`. Measured on b0c87cb (PR 322 review): 13 of 120 rows were lost at 3 writers with a shared temp name and no lock.

Cap: the last 200 rows (`MAX_LOG_LINES` in `janitor/agent_end_reap.py`).

Reader: `hooks/daily_note.py` (`agent_end_failures`), at the first startup of each Central day. It prints one line that counts the runs whose day is in the window and that have a `started` row with no `done` row, or a row with an `error`. A run whose rows the cap cut is not counted. `janitor/prove_agent_end_reap.py` reads the last row of the log in its own empty temp config dir.

Cost: each agent end rewrites the log twice, through a temp file and a replace, and takes the lock file (unmeasured). The log starts no process: its writer is the SubagentStop hook that already runs. The note reads the log once a day (unmeasured).
