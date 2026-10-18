# When a worktree may be removed

## The ruling

Four routes remove a worktree: the unattended `--confirm` run, and three routes that remove a tree under `.claude/worktrees/agent-*` without both of its conditions. Those three are the agent-end reap, the session-end sweep's agent rule, and the repository's own `reap:worktrees` script. A route removes a worktree only when every read of that route answers a confirmed yes. A read that cannot tell keeps the tree.

### Idle limits, side by side

Every idle limit reads idle the same way: the newest mtime of the worktree's own `index`, `HEAD` and `logs/HEAD`. A younger tree is kept. A time that cannot be read keeps the tree.

| Idle limit | Route | Case it governs |
|---|---|---|
| 30 min or more | Agent-end reap, at each SubagentStop | A finished agent's worktree. The ending agent's own worktree waits the same limit. |
| 1 hour | Unattended `--confirm` run: the daily job and SessionEnd | Every worktree this route removes, together with the merged-or-pushed test below. |
| 4 hours | Session-end sweep, agent rule (`sweep.py --confirm`, no `--attended`) | A finished agent's worktree at `<repo>/.claude/worktrees/agent-*`, in every repo. |
| 24 hours | Unattended `--confirm` run | A pushed tree, merged or not. |

Open for the owner: which limit governs a clean, pushed agent worktree that is not merged. Also open: whether the merged test of "Safe work" binds the agent-end reap and the agent rule, which test pushed only. Each rule stands as written until the owner rules.

### Safe work

- Remove only a clean folder where every commit on HEAD is on a remote branch (a detached HEAD counts). HEAD must also be merged into the default branch by ancestry or by patch (`a-branch-is-redundant-by-patch-not-by-ancestry`). With no remote, every worktree stays. The owner chose the patch check over a check of the lines on main today.
- This covers every worktree reap, locked or not. `--confirm` unlocks, then removes, never with `--force`. If removal fails, the sweep restores the lock.
- A stale agent lock is judged by the rule in `the-janitor-is-one-machine-wide-sweep`.
- Owner word, 2026-10-13 15:56 CDT: option A. The janitor's dirty test stays as it is. No junk-pattern change. Reaping dirty trees stays closed. The restore-point rule does not reopen it.
- Re-measure `q_max` after the lane `worktree-hook-paths` merges. It is unmeasured until then.

Reason: the dirty trees in this clone are live work. Most `q_max` leftovers come from false refusals in its worktree-remove hook, not from dirt.

### Unattended run

Owner ruling, 2026-10-01: every `--confirm` run, the daily job and SessionEnd included, needs both of these to remove a worktree:

- Merged, or pushed and idle 24 hours. Merged means HEAD holds no commit that the default branch lacks. The test is the redundancy test of `a-branch-is-redundant-by-patch-not-by-ancestry`, by ancestry or by patch, read in the worktree. A pushed tree has every commit on a remote branch that the remote lists now (`git ls-remote`, read-only). It is removed once it is idle 24 hours, merged or not (owner ruling, 2026-10-09), because the remote keeps every commit. A remote that cannot be read keeps the tree. Git-ignored files, a local secrets file too, are removed with the tree (owner ruling, 2026-10-09).
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
- Its tip is on GitHub. Two reads must both pass: `git ls-remote --heads` read now lists a head that holds HEAD (owner ruling 2026-10-14: the read is live, never a local `origin/*` ref alone), and `git branch -r --contains HEAD` is not empty.

A read that fails or cannot tell keeps the tree. The report line names its path and the reason `unreadable-subject`. A repo whose `package.json` defines the script `reap:worktrees` gets `npm run reap:worktrees -- --remove` run in its root instead of this rule. An unreadable `package.json` turns the rule off for that repo.

Reason: a lane pushes `HEAD:<lane>` from a local branch of another name, so a branch-upstream read called many trees never pushed. The test-author makes its red-proof checkout under `<repo>/.claude/worktrees/` and names it `agent-<something>`, so this rule covers it. A checkout with another name under that folder is not covered.

Kind: process
Home: janitor/sweep.py
Home: janitor/agent_end_reap.py
