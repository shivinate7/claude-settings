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
   harness or a terminal is such a parent. Read 3 applies in the ending agent's own worktree
   too.
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
- A process that a live parent outside the worktree holds is never stopped by the hook.
  The agent's own shells have the live host as parent, so they keep the tree (Part 4).

Owner ruling 3, 2026-09-27: this scope is accepted. The reaper stops each orphaned tree
inside an ended agent's worktree, not only listeners.

The guard's ownership change (owner ruling, 2026-10-10) changes the guard's kill rule
only. The reaper's reads stay as above. See `a-kill-by-pid-needs-an-owned-pid`.

## Part 4. The worktree is removed at agent end

Owner rulings, 2026-10-15 and 2026-10-16: plan step 3, the 19:43 CDT rulings below, and
"Wait 30 min too" (2026-10-16 00:47 CDT). Lane wt-reap builds this part.

Why. On 2026-10-15 the machine held 610 agent worktrees. The reaper stopped processes only.
Removal fell to the session-end sweep. The sweep costs about 7.5 s per tree. Its budget is
25 s, so it reaches about three trees a run. Debt `sweep-no-deadline-many-trees` tracks the gap.

Rule. At each SubagentStop, the reaper removes each finished agent's worktree that is idle
30 min or more. The ending agent's own worktree is not removed at its own end. It waits
30 idle minutes like the others. A later agent end, or the session-end sweep, removes it.

Idle is defined once, in `unattended-sweep-stops-proven-orphans` (an unattended sweep removes only proven orphans).

Why 30 min for the own tree too. A follow-up message to a finished agent resumes it in its
own worktree. A removed worktree makes the agent stop (decision
an-agent-outside-its-home-tree-must-stop, an agent outside its tree stops). The wait keeps
follow-ups working. (Owner ruling, 2026-10-16 00:47 CDT. It replaces the 23:00 CDT ruling
"Build a delayed remover". Lane wt-reap-delay is closed unbuilt.)

MEASURED 2026-10-15, Windows, lane wt-reap try 4: the hook cannot remove its own worktree.
Its own wrapper shells run with cwd inside the tree. `git worktree remove` gives rc 255
after it deletes the files. The 30 min wait removes this problem: a tree is removed only
from a later hook, whose cwd is in another tree.

The hook keeps main's Part 3 stops, read 3 in force, in the ending agent's tree. It stops an
orphan whose parent is dead. It never stops a process with a live parent, so the guard's
wrapper is never stopped. Part 3 targets only the ending agent's tree, so the hook stops
nothing in another tree, as on main.

The 19:43 CDT rulings: stop the finished agent's own shells, then remove the tree, even with
git-ignored files. The second half holds. The first half is not built. The agent's own
shells have the live host as parent, so no hook stops them. They keep the tree until the
host exits. Debt `finished-agent-shells-keep-tree`. (Owner ruling, 2026-10-15 19:43 CDT.)

A clean tree has no uncommitted and no untracked file. Git-ignored files do not keep a
tree. A clean, pushed worktree is removed even when it holds git-ignored files, such as
build output, packages or `.env.local`. (Owner ruling, 2026-10-15 19:43 CDT.)

A worktree is removed only when all of these hold:

- it is idle 30 min or more;
- it is clean;
- it is pushed;
- it is unlocked;
- no live session uses it (the constraint in Part 3);
- no process has a cwd inside it.

A read that cannot tell keeps the worktree.

Related, same ruling:

- Session start warns when more than 50 agent worktrees exist (lane wt-reap).
- Briefs stop leaving checkouts for the sweep. An agent leaves its worktree clean and
  pushed, and a later agent end removes it. The builder and test-author agent definitions
  say so.
- Sweep speed: one pass of git reads, a time limit, oldest first (lane sweep-fast).
- Drain today's pile of 610 (plan step 5). The ruling names no method.

Accepted cost: a resume of a finished agent fails once its worktree is gone, after 30 idle
minutes. A fresh agent gets the old report instead. Removal also deletes the tree's
git-ignored files, a copied `.env.local` included. The sweep's Limits note says the same.
The last agent's tree in a session waits for the session-end sweep or the next session.

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
- A tree that Part 4 removes with an uncommitted or untracked file, unpushed, locked, or in use.
- A process in another tree that the reaper stops.
- A reap that ends in `hook_cancelled` or `timedOut: true`.
- A batch read, or a full run on about 1,300 pids, that takes 60 s or more.

## Holes, named

Lane `sweep-fast` passed review round 3 with a positive net safety value. Each open finding is a debt:

- `sweep-no-deadline-many-trees`: the husk and trash scans run to their end once started. The per-root setup has no deadline check. Review round 3, item 1.
- `sweep-no-deadline-many-trees`: idle time is read for every tree before any judgment. Old kept trees can use the budget, so younger trees go unjudged. Review round 3, item 2.
- `sweep-skip-reads-as-clean`: a skipped scan reads as clean. The run log has no not-judged count. The summary has no trash UNKNOWN line. The listener line gives the wrong cause. The hook drops stdout. Review round 3, item 3.
- `sweep-no-deadline-many-trees`: idle is read up to about 12-20 s before a decision, against 1-3 s on main. Dirty, unpushed, live-session and process checks still keep a tree. Review round 3, item 4.
- `sweep-attended-idle-unused`: an attended run reads idle time it does not use. A preview may lose its thread pool. Review round 3, item 5.
- `sweep-no-deadline-many-trees`: the deadline is a fixed 12 s for any `--confirm` without `--attended`, until lane `sweep-budget` lands.

Lane `wt-reap` passed review round 3 with a positive net safety value. Each open finding is a debt:

- `finished-agent-lock-holds-tree`: a finished agent's worktree can hold `claude agent agent-<id> (pid N)`, with no start time. N is the session's live claude.exe. The lock looks like a running agent's lock. So the tree stays until the host exits. MEASURED 2026-10-15 23:31: 17 of 166 agent trees, later 22, all held by one pid. A fix needs a finished-agent proof that the ruling does not give. Owner decision.
- `marker-writeback-loses-deletion`: a failed remove leaves `claude-removal-started` on an intact tree. Later, at agent end, that tree is written back and removed. The tree must be idle 30 minutes, unlocked (or hold a stale agent lock), with no live session or process inside. It holds only unstaged deletions of tracked files. The person's uncommitted deletion is lost. Narrow: it needs a prior failed remove.
- `finished-agent-shells-keep-tree`: a finished agent's own shells, such as a dev server, have the live host as parent. No hook stops them, so they keep the tree until the host exits. The 19:43 CDT ruling to stop them is not built.
- `no-start-lock-has-no-pid-check`: the lock form with no start time has no pid-reuse check. The sweep frees it only when pid N is dead. A live process that holds a reused pid keeps the tree. That is the safe side. The janitor decision names this form.
