# Agent-end reap stops what a finished agent left

Kind: process
Home: janitor/agent_end_reap.py

Governing records: `unattended-sweep-stops-proven-orphans` (a sweep stops only proven orphans) and
`liveness-read-is-platform-specific-and-unreadable-is-not-death` (an unreadable read is
not death).

## The ruling

The goal: when a subagent ends, each process it left under its own worktree stops, and
that worktree is removed when Part 4 allows. Nothing else stops or is removed.

### Part 1. The guard refuses the three missed shapes

The `detached-launch` rule in hooks/guard.py also refuses these shapes:

- A bare `&` job in any segment, not only the last one. The pid must be captured with
  `$!` somewhere in the command, or the rule refuses. A leading `&` is PowerShell's call
  operator, so the rule reads only an `&` after the command word.
- `disown` in command position, on any line.
- The same shapes inside the script of `sh -c` or `bash -c`. The rule reads that script
  with the same checks.

The remedy is not changed. It tells the agent to use `run_in_background`. An `&` inside a heredoc body
is code, so the read drops each heredoc body first. The cost: an `&` job inside `bash <<EOF` is not seen.

### Part 2. The sweep takes the deepest checkout

`janitor/sweep.py` `_matching_checkout` returns the deepest checkout that holds the cwd, not the
primary checkout. No session record names a subagent, so a running subagent's worktree reads as "not
live". A server whose parent died could then be stopped by the sweep while its agent still runs.

Owner ruling 2, 2026-09-27: the sweep skips each process whose cwd is under a
`.claude/worktrees/*` checkout. It leaves those folders to janitor/agent_end_reap.py.
`find_swept_listeners` in janitor/sweep.py applies the skip.

### Part 3. The reaper

`janitor/agent_end_reap.py` is a hook. It runs on SubagentStop only and reads one hook payload.

- **SubagentStop** gives `agent_id`. The harness names the worktree `agent-<agent_id>`.
  The reaper looks for `<primary>/.claude/worktrees/agent-<agent_id>`. It finds the
  primary checkout from the payload `cwd` with `guard.primary_checkout`.

The target must have the shape `.claude/worktrees/<name>`. It must exist. It must not be
a primary checkout. An agent id must match `[A-Za-z0-9_-]{1,64}`.

The reaper stops one process only when each read below answers a confirmed yes:

1. The process cwd is inside the target. The cwds come from one batch read (owner
   ruling 4, 2026-10-10, below).
2. No live session has a cwd inside the target (`guard.worktree_live_session`).
3. The root of its process tree inside the target is orphaned. The reaper climbs from the
   process to each live parent whose cwd is also inside the target. Then it asks
   `sweep.is_orphan` about the last one. A live parent outside the target means keep. A
   harness or a terminal is such a parent. Read 3 applies in the ending agent's own worktree
   too.
4. The current user owns the process.

An unreadable read means keep. The signal goes by pid through `sweep.send_signal`, once.

Reason for read 3: an MSYS bash stub whose own parent is dead is orphaned, so the reaper stops the
server and the stub. A `run_in_background` task of a live agent hangs from a live `claude.exe` outside
the worktree, so the reaper keeps it.

The owner's constraints hold:

- Ownership is judged by the checkout that holds the cwd, never by a name.
- The primary checkout is never a target.
- A worktree that a live session uses is never touched.
- A process that a live parent outside the worktree holds is never stopped by the hook.
  The agent's own shells have the live host as parent, so they keep the tree (Part 4).

Owner ruling 3, 2026-09-27: the reaper stops each orphaned tree inside an ended agent's worktree, not
only listeners.

The guard's ownership change (owner ruling, 2026-10-10) changes the guard's kill rule
only. The reaper's reads stay as above. See `a-kill-by-pid-needs-an-owned-pid`.

### Part 4. The worktree is removed at agent end

Owner rulings, 2026-10-15 and 2026-10-16, including "Wait 30 min too" (2026-10-16 00:47 CDT).

Rule. At each SubagentStop, the reaper removes each finished agent's worktree that is idle 30 min or
more. The ending agent's own worktree is not removed at its own end. It waits the same idle limit as the
others. A later agent end, or the session-end sweep, removes it. Reason: the hook cannot remove the tree
its own shells stand in, so a tree is removed only from a later hook, whose cwd is in another tree.

Idle is defined once, in `unattended-sweep-stops-proven-orphans` (an unattended sweep removes only proven orphans).

Why 30 min for the own tree too. A follow-up message to a finished agent resumes it in its
own worktree. A removed worktree makes the agent stop (decision
an-agent-outside-its-home-tree-must-stop, an agent outside its tree stops). The wait keeps
follow-ups working.

The hook keeps Part 3's stops, read 3 in force, in the ending agent's tree. It stops an
orphan whose parent is dead. It never stops a process with a live parent, so the guard's
wrapper is never stopped. Part 3 targets only the ending agent's tree, so the hook stops
nothing in another tree.

The 19:43 CDT rulings (2026-10-15): stop the finished agent's own shells, then remove the tree, even with
git-ignored files. The second half holds. The first half is not built. The agent's own
shells have the live host as parent, so no hook stops them. They keep the tree until the
host exits. Debt `finished-agent-shells-keep-tree`.

A clean tree has no uncommitted and no untracked file. Git-ignored files do not keep a
tree. A clean, pushed worktree is removed even when it holds git-ignored files, such as
build output, packages or `.env.local`.

A worktree is removed only when all of these hold:

- it is idle for the Rule's limit;
- it is clean;
- it is pushed;
- it is unlocked;
- no live session uses it (the constraint in Part 3);
- no process has a cwd inside it.

A read that cannot tell keeps the worktree.

Related, same ruling:

- Session start warns when more than 50 agent worktrees exist.
- Briefs stop leaving checkouts for the sweep. An agent leaves its worktree clean and
  pushed, and a later agent end removes it. The builder and test-author agent definitions
  say so.
- Sweep speed: one pass of git reads, a time limit, oldest first.

Accepted cost: a resume of a finished agent fails once its worktree is gone, after the idle limit. A
fresh agent gets the old report instead. Removal also deletes the tree's git-ignored files, a copied
`.env.local` included. The last agent's tree in a session waits for the session-end sweep or the next
session.

### The reap reads every cwd in one batch

Owner ruling 4, 2026-10-10: the reap reads every process's cwd in one batch call. A run finishes well
inside the 60 s hook cap. Reason: a reap that hit the hook cap sent no signal and left a server running.

- `sweep._read_all_cwds_macos` makes one `lsof -d cwd -Fpn` call. It returns `[(pid, cwd)]`, or None on
  a failed or empty read. None means keep.
- The batch timeout is 30 s (`agent_end_reap.BATCH_TIMEOUT`). It sits below the hook cap, so a hung
  `lsof` ends as `unreadable-subject`, not at the cap.
- The reaper runs with the preview cache off (`_RUN` unset), so its read is fresh. A run that acts keeps
  it that way.
- The run writes a `started` row first and replaces it with the `done` row, so a killed run leaves a
  trace.

### Payload log

Each run appends one JSON line to `${CLAUDE_CONFIG_DIR:-~/.claude}/state/agent-end-payloads.jsonl`.
The line holds the raw payload, the target, and each decision. The file keeps the last 200 lines. The
hook always exits 0.

### The sweep removes a finished agent worktree

Owner ruling, 2026-10-14: the session-end sweep (`sweep.py --confirm`, no `--attended`)
removes a finished agent's worktree in every repo. It ADDS to the removals of
`unattended-sweep-stops-proven-orphans` (an unattended sweep removes only proven orphans).
It never narrows them. It removes a tree only when all of these hold:

- Its path is `<repo>/.claude/worktrees/agent-*`, a branch or a detached HEAD.
- It is clean: no uncommitted and no untracked file.
- It is unlocked, no live session and no process has a cwd inside it.
- It is idle 4 hours.
- Its tip is on GitHub. Two reads must both pass: `git ls-remote --heads` read now lists a
  head that holds HEAD (owner ruling 2026-10-14: the read is live, never a local
  `origin/*` ref alone), and `git branch -r --contains HEAD` is not empty.

A read that fails or cannot tell keeps the tree. The report line names its path and the
reason `unreadable-subject`. A repo whose `package.json` defines the script
`reap:worktrees` gets `npm run reap:worktrees -- --remove` run in its root instead of
this rule. npm is found with `shutil.which`. An unreadable `package.json` turns the rule
off for that repo.

Reason: a lane pushes `HEAD:<lane>` from a local branch of another name, so a branch-upstream read
called many trees never pushed. The remote keeps every commit of a removed tree. The test-author makes
its red-proof checkout under `<repo>/.claude/worktrees/` and names it `agent-<something>`, so this rule
covers it. A checkout with another name under that folder is not covered. `git worktree remove` deletes
the git-ignored files in a removed tree, a copied `.env` included, as the older rules already do.

### What reopens it

- A payload in the log that disagrees with the fields above.
- A subagent worktree name that is not `agent-<agent_id>`.
- A server that a live agent needed, stopped by this reaper or the sweep.
- A tree that Part 4 removes with an uncommitted or untracked file, unpushed, locked, or in use.
- A process in another tree that the reaper stops.
- A reap that ends in `hook_cancelled` or `timedOut: true`.
- A batch read, or a full run on about 1,300 pids, that takes 60 s or more.
