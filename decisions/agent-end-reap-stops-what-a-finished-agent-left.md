# Agent-end reap stops what a finished agent left

Kind: process
Home: janitor/agent_end_reap.py

This record is step 2 of the plan in `which-start-shapes-outlive-the-agent-on-windows`
(start shapes that outlive a subagent on Windows; PR #144). That record measured the
shapes. This record holds the fix. Governing records:
`unattended-sweep-stops-proven-orphans` (a sweep stops only proven orphans) and
`liveness-read-is-platform-specific-and-unreadable-is-not-death` (an unreadable read is
not death).

The goal: when a subagent ends, each process it left under its own worktree stops, and
that worktree is removed when Part 4 allows. Nothing else stops or is removed.

## Part 1. The guard refuses the three missed shapes

The `detached-launch` rule in hooks/guard.py also refuses these shapes:

- A bare `&` job in any segment, not only the last one. The pid must be captured with
  `$!` somewhere in the command, or the rule refuses. A leading `&` is PowerShell's call
  operator, so the rule reads only an `&` after the command word.
- `disown` in command position, on any line.
- The same shapes inside the script of `sh -c` or `bash -c`. The rule reads that script
  with the same checks.

The remedy is not changed. It tells the agent to use `run_in_background`.

## Part 2. The sweep takes the deepest checkout

`janitor/sweep.py` `_matching_checkout` now returns the deepest checkout that holds the
cwd. Before, it returned the first one, and that was the primary checkout.

This change moves one verdict. A listener in an agent worktree is now judged against the
live sessions of that worktree, not those of the primary checkout. No session record names
a subagent. So a running subagent's worktree reads as "not live". The orphan read still
keeps each server whose parent is alive. A server whose parent died, such as one from
`Start-Process -PassThru`, could then be stopped by the sweep while its agent still runs.

Owner ruling 2, 2026-09-27: the sweep skips each process whose cwd is under a
`.claude/worktrees/*` checkout. It leaves those folders to janitor/agent_end_reap.py.
`find_swept_listeners` in janitor/sweep.py applies the skip. The case
`test_the_sweep_leaves_an_orphan_in_an_agent_worktree_to_the_reaper` went red on a `.bak`
copy without the skip. janitor/mutate_sweep.py carries one mutant for it.

## Part 3. The reaper

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
   harness or a terminal is such a parent.
4. The current user owns the process.

An unreadable read means keep. The signal goes by pid through `sweep.send_signal`, once.

Read 3 solves the MSYS stub. The server's parent is a live bash stub, and the stub's cwd
is the worktree. The stub's own parent is dead. So the climb reaches the stub, and the
stub is orphaned. The reaper stops the server and the stub. A `run_in_background` task of
a live agent hangs from a live `claude.exe` outside the worktree. So the reaper keeps it.

The owner's constraints hold:

- Ownership is judged by the checkout that holds the cwd, never by a name.
- The primary checkout is never a target.
- A worktree that a live session uses is never touched.
- A process that a live parent outside the worktree holds is never touched.

Owner ruling 3, 2026-09-27: this scope is accepted. The reaper stops each orphaned tree
inside an ended agent's worktree, not only listeners.

The guard's ownership change (owner ruling, 2026-10-10) changes the guard's kill rule
only. The reaper's reads stay as above. See `a-kill-by-pid-needs-an-owned-pid`.

## Part 4. The worktree is removed at agent end

Owner ruling, 2026-10-15 (plan step 3). Status: decided, not built. Lane wt-reap builds it.
Until that lane merges, the reaper stops processes and removes no worktree.

Why. On 2026-10-15 the machine held 610 agent worktrees. The reaper stopped processes only.
Removal fell to the session-end sweep. The sweep costs about 7.5 s per tree. Its budget is
25 s, so it reaches about three trees a run. Debt `sweep-no-deadline-many-trees` tracks the gap.

Rule. At each SubagentStop, the reaper removes two kinds of worktree:

- the ending agent's own worktree, `agent-<agent_id>`;
- each other finished agent's worktree that is idle 30 min or more.

Idle is read as the sweep reads it (see "The sweep removes a finished agent worktree").
A worktree is removed only when all of these hold:

- it is clean;
- it is pushed;
- it is unlocked;
- no process has a cwd inside it;
- no live session uses it (the constraint in Part 3).

A read that cannot tell keeps the worktree.

Related, same ruling:

- Session start warns when more than 50 agent worktrees exist (lane wt-reap).
- Briefs stop leaving checkouts for the sweep. An agent leaves its worktree clean and
  pushed, and agent end removes it. The builder and test-author agent definitions say so.
- Sweep speed: one pass of git reads, a time limit, oldest first (lane sweep-fast).
- Drain today's pile of 610 (plan step 5). The ruling names no method.

Accepted cost: a resume of a finished agent fails once its worktree is gone. A fresh agent
gets the old report instead.

## Reap timeout, 2026-10-10

Incident: in feed-build session c52856af, a reviewer's vite server (pids 50092 and 50189,
port 5299) outlived its agent. The SubagentStop reap hit the 60 s hook timeout before it
sent a signal. The harness logged `hook_cancelled` with `timedOut: true`. That session had
12 such timeouts. The parent session could not stop the server. The guard counts a process
as owned only by ancestry (`a-kill-by-pid-needs-an-owned-pid`), and the server had PPID 1.
The owner stopped it by hand.

Cause (inferred from code; partly unmeasured). `decide()` calls `sweep.process_cwd(pid)` once per pid. On
macOS each call starts one `lsof`. The 27 ms per pid was measured on 2026-10-10. Over
about 1,300 pids that is about 35 s. A code comment in `_read_all_cwds_macos`
(janitor/sweep.py, undated) puts the per-pid pass near 25 s. Both figures are under the
60 s cap. So the per-pid pass alone does not explain 12 timeouts. Unmeasured: the machine
load at each timeout, and any read beyond the cwd pass. The builder's timed run settles the cause.

Owner ruling 4, 2026-10-10: the reap reads every process's cwd in one batch call. A run
finishes well inside 60 s.

Constraints for the batch read:

- `sweep._read_all_cwds_macos` already makes one `lsof -d cwd -Fpn` call. It returns
  `[(pid, cwd)]`, or None on a failed or empty read. None means keep.
- Its subprocess timeout is 60 s, the same as the hook cap. A hung `lsof` would end the
  hook at the cap, not as `unreadable-subject`. The batch timeout must sit below the cap.
- The reaper runs with the preview cache off (`_RUN` unset), so its read is fresh. A run
  that acts must keep it that way.
- Linux reads `/proc` per pid, with no subprocess. Windows reads per pid. Cost on both:
  unmeasured.

Proof owed: a test that counts process reads in `decide()` and fails when the count grows
with the pid count. It goes red on the per-pid code first. Then one full run on the
feed-build machine, about 1,300 pids, timed under 60 s.

MEASURED 2026-10-10, this Mac, 1,004 pids, read-only `decide()` with no signal: 0.4 s in all
(batch `lsof` 0.3 s for 795 cwd lines; pid list and `worktree_live_session` under 0.05 s each).
The batch timeout is 30 s (`agent_end_reap.BATCH_TIMEOUT`). Unmeasured: a run at 1,300 pids
on the feed-build machine. MEASURED: the timed-out hook was `agent_end_reap.py` itself
(`hook_cancelled`, durationMs 60402, 01:15:44Z) and it left no payload row, so it never reached
`log()`. INFERRED, not measured: 7 simulators held about 15 GB and free memory was 27%, so 1,300
separate `lsof` spawns ran far slower than 27 ms each. The run now writes a `started` row first
and replaces it with the `done` row, so a killed run leaves a trace. The 12 timeouts were not explained by the per-pid pass alone (above).

## Payload log

Each run appends one JSON line to `${CLAUDE_CONFIG_DIR:-~/.claude}/state/agent-end-payloads.jsonl`.
The line holds the raw payload, the target, and each decision. The hook fields that the
docs leave open get measured from this log. The file keeps the last 200 lines (the cap
in `guard-trims-from-the-audit`). The hook always exits 0.

## The sweep removes a finished agent worktree

Owner ruling, 2026-10-14: the session-end sweep (`sweep.py --confirm`, no `--attended`)
removes a finished agent's worktree in every repo. It ADDS to the removals of
`unattended-sweep-stops-proven-orphans` (merged and idle 1 hour, or pushed and idle 24
hours). It never narrows them. It removes a tree only when all of these hold:

- Its path is `<repo>/.claude/worktrees/agent-*`, a branch or a detached HEAD.
- It is clean: no uncommitted and no untracked file.
- It is unlocked, no live session and no process has a cwd inside it.
- It is idle 4 hours. Idle is the newest mtime of the tree's `index`, `HEAD` and
  `logs/HEAD`.
- Its tip is on GitHub. Two reads must both pass: `git ls-remote --heads` read now lists a
  head that holds HEAD (owner ruling 2026-10-14: the read is live, never a local
  `origin/*` ref alone), and `git branch -r --contains HEAD` is not empty.

A read that fails or cannot tell keeps the tree. The report line names its path and the
reason `unreadable-subject`. A repo whose `package.json` defines the script
`reap:worktrees` gets `npm run reap:worktrees -- --remove` run in its root instead of
this rule. npm is found with `shutil.which`. An unreadable `package.json` turns the rule
off for that repo.

Why: q_max held 798 registered worktrees. A lane pushes `HEAD:<lane>` from a local branch
of another name, so a branch-upstream read called 181 of them never pushed. The remote
keeps every commit of a removed tree. The test-author makes its red-proof checkout under
`<repo>/.claude/worktrees/` and names it `agent-<something>`, so this rule covers it. A
checkout with another name under that folder is not covered.

Limits: `git worktree remove` deletes the git-ignored files in a removed tree, a copied
`.env` included, as the older rules already do. This rule keeps that behaviour.

The mechanism: `janitor/sweep.py`'s `_is_agent_worktree`, `_agent_rule_keep`, `repo_reaper`
and `run_repo_reaper`. `janitor/test_sweep.py`'s `AgentWorktreeReapTests` proves it.
`janitor/mutate_sweep.py` carries 12 mutants for it.

## Proof

`janitor/prove_agent_end_reap.py` builds a throwaway repo. It starts one server in
`agent-<A>`, one in `agent-<B>`, and one in the primary checkout. Each uses the shape
measured to outlive the agent. Then it fires a SubagentStop payload for A.

MEASURED on 2026-09-26, Windows 11, Git Bash, Python 3.14:

| Run | Agent A server | Agent B server | Primary server | Verdict |
|---|---|---|---|---|
| `--old`, only `sweep.py --confirm` | alive | alive | alive | FAIL |
| the reaper, SubagentStop for A | gone | alive | alive | PASS |

In the green run, the reaper stopped two pids in A: the bash stub and the server. So the
stub's cwd is the worktree. That was unmeasured before. Each run stopped all 6 pids it
started, by pid, with 0 left alive.

## Guard measurement

The old guard allowed all 7 new deny cases in hooks/test_guard.py. The new guard denies
them. The suite went red on the old guard, 7 of 594 cases wrong.

Replayed against 13312 distinct local Bash commands, in 118 sessions: the first draft
refused 6 commands that the old rule allowed. Each one was an `&` inside a python heredoc
body. That `&` is Python code. So the `&` read now drops each heredoc body first. After
that change, 0 commands are newly refused. The cost: an `&` job inside `bash <<EOF` is not
seen.

The deepest-checkout case in janitor/test_sweep.py went red on the old sweep.
hooks/mutate_guard.py and janitor/mutate_sweep.py carry one mutant for each new rule and
for each reaper refusal.

CI on 4864d83 found one survivor: the mutant that drops the `& disown` clause. The
any-segment `&` read also denies `cmd & disown`, so that case did not prove the clause.
The mutant now requires the case `python3 server.py & disown $!`. The `$!` satisfies the
`&` read, so only the `& disown` clause denies it. MEASURED 2026-09-27: that mutant alone
gives 1 of 596 cases wrong, and that case is the only one. The full harness ran past its
1200 s suite timeout on this machine, so its local count is unmeasured.

## What reopens it

- A payload in the log that disagrees with the fields above.
- A subagent worktree name that is not `agent-<agent_id>`.
- A server that a live agent needed, stopped by this reaper or the sweep.
- A tree that Part 4 removes while it is dirty, unpushed, locked, or in use.
- A reap that ends in `hook_cancelled` or `timedOut: true`.
- A batch read, or a full run on about 1,300 pids, that takes 60 s or more.
