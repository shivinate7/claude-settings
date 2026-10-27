# When a worktree may be removed

## The ruling

Four idle limits. 30 min: agent-end reap. 1 h: unattended `--confirm`, a merged tree. 4 h: session-end agent rule. 24 h: unattended `--confirm`, a pushed tree that is not merged. Pushed is enough (HEAD need not be merged) for the agent-end reap and the `agent-*` rule only. A dirty tree is never reaped.

Five routes remove a worktree. One is the unattended `--confirm` run. Three remove a tree under `.claude/worktrees/agent-*` without both of its conditions: the agent-end reap, the session-end sweep's agent rule, and a repo's own `reap:worktrees` script. That script keeps its own tests. The merge tool also removes the worktree that holds the branch it merged (owner, 2026-10-25, step c44). It calls the sweep's `--fast` judgment with `--attended` for that one tree, so there is no idle wait. The tree goes when it is clean and its HEAD is in the merged head. No lock, session or process may hold it, and it may not be the caller's cwd. A failed read keeps the tree, except one process whose cwd cannot be read: it is out of scope, not inside.

### Idle limits, side by side

Every idle limit reads idle the same way: the newest mtime of the worktree's own `index`, `HEAD` and `logs/HEAD`. A younger tree is kept. A time that cannot be read keeps the tree.

| Idle limit | Route | Case it governs | Why this limit |
|---|---|---|---|
| 30 min or more | Agent-end reap, at each SubagentStop | A finished agent's worktree. The ending agent's own worktree waits the same limit. | A follow-up message to a finished agent resumes it in its own worktree. A hook cannot remove the tree its own shells stand in. |
| 1 hour | Unattended `--confirm` run: the daily job and SessionEnd | Every worktree this route removes, together with the merged-or-pushed test below. | Unrecorded. |
| 4 hours | Session-end sweep, agent rule (`sweep.py --confirm`, no `--attended`) | A finished agent's worktree at `<repo>/.claude/worktrees/agent-*`, in every repo. | Unrecorded. |
| 24 hours | Unattended `--confirm` run | A pushed tree that is not merged. A merged tree goes at 1 hour. | Pushed proves that a copy exists, not that the work is done. The remote keeps every commit. |

Each route keeps its own limit. A clean, pushed agent worktree that is not merged is governed by the agent-end reap (30 min) and the agent rule (4 hours). The unmerged 24-hour limit applies to it only on the unattended run.

### Safe work

- Remove only a clean folder where every commit on HEAD is on a remote branch (a detached HEAD counts). Pushed is enough for the agent-end reap and the session-end `agent-*` rule: HEAD need not be merged into the default branch (owner ruling, 2026-10-18 02:03 CDT). The unattended run needs more, as below. With no remote, every worktree stays. A route may add a merged or idle test of its own, as the unattended run does below. A repo's own `reap:worktrees` script keeps its own tests.
- This covers every worktree reap, locked or not. `--confirm` unlocks, then removes, never with `--force`. If removal fails, the sweep restores the lock. After a cut-short remove, `_restore_cut_short` writes the deleted tracked files back from the index, never with `--force` (owner, 2026-10-15, review point 4).
- A stale agent lock is judged by the rule in `the-janitor-is-one-machine-wide-sweep`.
- Owner grant, 2026-10-13 15:56 CDT: option A. The janitor's dirty test stays as it is. No junk-pattern change. Reaping dirty trees stays closed. The restore-point rule does not reopen it.
- Re-measure `q_max` after the lane `worktree-hook-paths` merges. It is unmeasured until then.
- Fetch, owner ruling 2026-10-19 (CDT): `sweep.py` runs `git fetch --prune` in each repo before it judges a tree. It moves only remote-tracking refs. It drops a remote head the clone lacks, and keeps no tree as unreadable for it. Why: a local `origin/*` ref lags the remote, and the live read cannot test a head the clone lacks.
  - Orchestrator's call, 2026-10-19: the fetch runs in preview mode too.
  - Orchestrator's call, 2026-10-19: it passes `--no-tags`. Its timeout is 10 s, or the time left to the run deadline if that is less.
  - Orchestrator's call, 2026-10-19: a failed fetch adds `: fetch failed` to the reason of a tree kept as `unreadable-subject`. It keeps no other tree. The sweep judges other trees on the refs as they stand.

Reason: the dirty trees in this clone are live work. Most `q_max` leftovers come from false refusals in its worktree-remove hook, not from dirt.

### Unattended run

Owner ruling, 2026-10-01: every `--confirm` run, the daily job and SessionEnd included, needs both of these to remove a worktree:

- Merged, or pushed and idle 24 hours. Merged means HEAD holds no commit that the default branch lacks. The test is the redundancy test of `a-branch-is-redundant-by-patch-not-by-ancestry`, by ancestry or by patch, read in the worktree. A pushed tree has every commit on a remote branch that the remote lists now (`git ls-remote`, after the run's fetch, see Safe work). A listed head that the clone lacks is dropped: it cannot hold a commit of the tree. It is removed once it is idle 24 hours, merged or not (owner ruling, 2026-10-09), because the remote keeps every commit. A remote that cannot be read keeps the tree. Git-ignored files, a local secrets file too, are removed with the tree (owner ruling, 2026-10-09).
- Idle 1 hour.

The worktree must also be clean and fully pushed. No live session and no process may be inside. An unreadable process is judged by `unattended-sweep-stops-proven-orphans`. The lock must be gone, or its host process must be gone.

Strict is the default. A job that an older installer wrote passes no flag, so it is strict at once, with no reinstall. A person who wants the old rules passes `--attended`. The launchd plist, the Task Scheduler task and the SessionEnd hook never pass it. The agent-end reap takes no flag.

Reason: pushed proves that a copy exists. It does not prove that the work is done. The reasons for the other conditions are in `the-janitor-is-one-machine-wide-sweep`.

### Agent-end reap

Owner rulings, 2026-10-15 and 2026-10-16 (including the 30 min wait, 00:47 CDT).

At each SubagentStop, the reaper (`janitor/agent_end_reap.py`) removes each finished agent's worktree that is idle 30 min or more. The ending agent's own worktree is not removed at its own end. It waits the same idle limit as the others. A later agent end, or the session-end sweep, removes it. Reason: the hook cannot remove the tree its own shells stand in, so a tree is removed only from a later hook, whose cwd is in another tree. The wait also keeps follow-ups working: a message to a finished agent resumes it in its own worktree, and a removed worktree makes the agent stop (`an-agent-outside-its-home-tree-must-stop`).

Owner ruling, 2026-10-15 19:43 CDT: remove the tree even when it holds git-ignored files, such as build output, packages or `.env.local`. The same ruling wants the agent's own shells stopped first. That half is the debt `finished-agent-shells-keep-tree`.

A worktree is removed only when all of these hold. A read that cannot tell keeps it.

- It is idle 30 min or more.
- It is clean: no uncommitted and no untracked file.
- It is pushed and unlocked.
- No live session uses it (read 2 of the reaper, `agent-end-reap-stops-what-a-finished-agent-left`), and no process has a cwd inside it.

Session start warns when more than 50 agent worktrees exist. An agent leaves its worktree clean and pushed, and a later agent end removes it. The builder and test-author agent definitions say so.

### Session-end sweep, agent rule

Owner ruling, 2026-10-14: the session-end sweep (`sweep.py --confirm`, no `--attended`) removes a finished agent's worktree in every repo. It ADDS to the removals of the unattended run. It never narrows them. It removes a tree only when all of these hold:

- Its path is `<repo>/.claude/worktrees/agent-*`, a branch or a detached HEAD.
- It is clean, unlocked, and idle 4 hours. No live session and no process has a cwd inside it.
- Its tip is on GitHub, read after the run's fetch (see Safe work). Two reads must both pass: `git ls-remote --heads` read now lists a head that holds HEAD (owner ruling 2026-10-14: the read is live, never a local `origin/*` ref alone; a listed head the clone lacks is dropped), and `git branch -r --contains HEAD` is not empty.

A read that fails or cannot tell keeps the tree. The report line names its path and the reason `unreadable-subject`. A repo whose `package.json` defines the script `reap:worktrees` gets `npm run reap:worktrees -- --remove` run in its root instead of this rule. An unreadable `package.json` turns the rule off for that repo.

Reason: a lane pushes `HEAD:<lane>` from a local branch of another name, so a branch-upstream read called many trees never pushed. The test-author makes its red-run checkout under `<repo>/.claude/worktrees/` and names it `agent-<something>`, so this rule covers it. A checkout with another name under that folder is not covered.

Kind: process
Home: janitor/sweep.py
Home: janitor/agent_end_reap.py
