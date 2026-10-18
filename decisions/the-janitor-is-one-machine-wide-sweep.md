# The janitor is one machine-wide sweep

## The ruling

The sweep deletes a local branch that holds no unique work. It also removes a spent worktree.

**One copy, in `janitor/`.** The subject is the machine: the liveness oracle reads `~/.claude/sessions`, and worktrees sit under many repositories. Five copies are five things that can each be wrong about one machine. The directory joins `landed-dirs.txt` and `CONFIG_FROZEN_DIRS` in `hooks/guard.py` in the same change. A session must not rewrite a program that deletes branches.

**Parent and child.** The parent ships branches and worktrees: pure git plus the oracle. A child repository keeps its own process tier and service teardown, because they name its own files, servers and launchd labels. This repository ships the guide for writing one. Banchi keeps its own tier 2 until the owner names its removal. Two process tiers are generic and live here:

- `find_loose_processes` is report only. Its subject is an orphaned process whose argv contains a shell-snapshots path. A live session's wrapper is noise, so it is not listed.
- `find_dead_rooted` stops only a proven orphan that the current user owns. Its subject is a process whose script file and parent directory are gone, under a deleted checkout.

**Stale registrations are pruned by git's own word.** The prune tier runs `git worktree prune -n -v`, acts only on what that names, and only under `--confirm`. It runs before the worktree list is read. The sweep keeps no second rule for "stale".

**A stale agent lock does not keep a worktree.** The Agent tool locks each lane worktree with the host Claude pid, not the agent's. A lane always commits, so the lock outlives the agent. The sweep frees a worktree from such a lock only when the host pid is dead, or alive with another start time, and the worktree passes every other check. A lock with no start time is freed only when its pid is dead. Any other lock reason, and any unreadable fact, keeps the tree.

**Safe work.** Remove only a folder that is clean and whose work is safe:

- Every commit on HEAD is on a remote branch. A detached HEAD counts.
- HEAD is merged into the default branch by ancestry or by patch (`a-branch-is-redundant-by-patch-not-by-ancestry`). So a squash-merged lane whose branch was deleted is removable. The merged exemption needs a remote. With none, every worktree stays.

The owner chose the patch check over a check of the lines on main today. This covers every worktree reap, locked or not. Every `--confirm` run also applies the limits of `unattended-sweep-stops-proven-orphans`. `--confirm` unlocks, then removes, never with `--force`. If removal fails, the sweep restores the lock.

**Every automatic run leaves a trace.**

- A `--confirm` run appends one line per repository to `${CLAUDE_CONFIG_DIR:-~/.claude}/state/janitor-runs.jsonl`: removed worktrees, reaped branches, free disk bytes. A preview writes nothing.
- The sweep lists entries under `<root>/.claude/worktrees/` that git does not register as strays. It never deletes them.
- Idle is git's admin-file idle time, not folder mtime. The sweep removes a worktree with git and never calls a repository's WorktreeRemove hook.

**A branch leaves "checked out" with its worktree, in the same run.** A removed worktree frees its branch, and the sweep judges it by the normal no-unique-work rules in that run. A preview does this for a worktree marked REAP. A kept worktree, or a failed removal, keeps its branch held.

**Two single-tier modes serve a hook.**

- `--tier1` prunes stale registrations and deletes husks. It is the one mode that acts without `--confirm`, and it removes only proven junk.
- `--branches` reaps branches only. It holds every worktree's branch, and refuses the repository if git gives no worktree list.

**Leftover folders are deleted only when proven twice.** `find_husks` finds a real folder under `.claude/worktrees/` that git does not list and that holds only names the repository gives in `huskNames`. The repository knows its own build output; the sweep does not. Only `--confirm` deletes, and only after the proof runs again right before the delete. The sweep never follows a link and walks only the repository's own `.claude/worktrees`. Any error, and an empty process table, keeps the folder. On Windows, `sweep.is_link` reads a junction from the reparse-point flag (`build-dirs-reaped-at-agent-end`).

**The sweep never runs code a repository supplies.** A repository states its wishes in `.claude/janitor.json`, read as data. A repository that supplies code to a frozen tool can do everything that tool can do.

**The sweep is automatic, and a repository opts out.** It visits every repository that carries no opt-out file. The opt-out file is `.claude/janitor.json`, inside the repository, so it travels with a clone. It carries more than a yes or a no, so a bare marker cannot do the job. The repository that pays the cost holds its own consent. An absent file means swept. The tombstone makes a lost branch recoverable. The keys are in the janitor guide.

**The default branch.** The sweep judges each repository against its own default branch, read in the order of `default-branch-read-order`. If none answers, the sweep refuses the repository out loud and reaps nothing there.

**Two triggers.** A `SessionEnd` hook sweeps only the repository whose session ended. A daily scheduled job sweeps every repository. The hook fails open, because a hook that can refuse the end of a session is worse than a leak. The installers write the job definition outside the repository and refuse to run from a linked worktree.

**A reaped branch leaves a tombstone.** Before the delete, the sweep writes `refs/janitor/reaped/<branch>` at the tip and appends one line to a restore log: repository, branch, commit id, time. The commits stay reachable, so `git gc` cannot take them. The purge drops a tombstone after 90 days, aged by the restore log's own timestamp, never by the ref's mtime (`purge-keeps-younger-restore-ref`). The 90 days beat git's own 30-day expiry of an unreachable reflog entry.

**Liveness.** Liveness comes from `~/.claude/sessions/*.json`. A record counts as live only when the id is alive and the recorded start time still matches, so a recycled id cannot inherit a dead session's claim. The oracle compares the start time as epoch milliseconds.

**How the sweep is proven.**

- Each refusal gets a test arm that violates it. Every arm asserts that its subject set is not empty before it asserts a verdict. Each assertion is mutated to show that it fails.
- The anchor arm is the rebase ghost. It must go red against a keep rule that tests ancestry alone. The liveness arm holds a record whose stored start time does not match the live id, and must read it as dead.
- Each new rule gets a row in `lint/rule_mechanisms.json`, or an argued `unmechanized` row.
- `lint/check_landed_dirs.py` holds the manifest and the frozen list in agreement. `janitor/test_sweep.py` proves the sweep itself.

Kind: process
Home: janitor/sweep.py
