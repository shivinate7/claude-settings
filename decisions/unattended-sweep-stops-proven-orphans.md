# Unattended sweep stops proven orphans

## The ruling

**What an unattended run can stop.** A `--confirm` run, run by the SessionEnd hook or the scheduled task, can send one signal to one process. All of these must be true first:

- The process is orphaned. The read is per-OS and answers three states: orphaned, not orphaned, or unreadable.
- No live Claude session has a cwd in the same checkout. `guard.worktree_live_session` is the oracle. This sweep never re-derives that answer.
- The process is owned by the account running the sweep.

The signal is SIGTERM on Linux and macOS, and `TerminateProcess` on Windows. Both go by pid, never by a name or a pattern. The sweep never sends a second, stronger signal on its own.

**No arm flag, every checkout.** Owner, 2026-09-24: both unattended paths may stop a proven orphan with no separate arm flag, in every checkout. A primary checkout gets no exemption. The three reads above are the whole gate. Reason: a stopped process cannot come back, but a reaped branch keeps a tombstone and a kept worktree stays whole.

**A process this sweep cannot read is out of scope.** It is counted. It is never acted on, and never a reason to keep something else. `decide_worktree`'s pre-removal check asks whether any process sits inside a worktree. A single process whose cwd cannot be read never blocks a removal. Only the WHOLE pid enumeration failing means keep-everything. Reason: on a real machine many processes belong to another account, so keeping on any one of them would refuse to reap anything.

**An unattended run may remove a worktree.** Owner ruling, 2026-10-01: every `--confirm` run, the daily job and SessionEnd included, needs both of these to remove a worktree:

- Merged, or pushed and idle 24 hours. Merged means HEAD holds no commit that the default branch lacks. The test is the redundancy test of `a-branch-is-redundant-by-patch-not-by-ancestry`, by ancestry or by patch, read in the worktree. A detached HEAD counts by its commit. A pushed tree has every commit on a remote branch. It is removed once it is idle 24 hours, merged or not (owner ruling, 2026-10-09), because the remote keeps every commit. Before that, the keep reason is `unmerged`. Pushed means reachable from a head that the remote lists now (`git ls-remote`, read-only), because a local `origin/*` ref can name a branch that the remote deleted. A remote that cannot be read keeps the tree.
- Idle 1 hour. Idle is the newest mtime of the worktree's own `index`, `HEAD` and `logs/HEAD`, under `.git/worktrees/<name>`. Every idle limit of the sweep and of the agent rules reads it this way. The sweep reads it before any `git status`, which can rewrite the index. A younger tree is kept, with reason `recently-active`. A time that cannot be read keeps the tree, with reason `unreadable-subject`.

Three other routes remove a tree under `.claude/worktrees/agent-*` without both. All three are in `agent-end-reap-stops-what-a-finished-agent-left`:

- The sweep's agent rule: a clean, pushed `agent-*` tree idle 4 hours.
- The repo's own `reap:worktrees` script. The sweep runs it in place of the agent rule.
- The agent-end removal: the SubagentStop reaper removes an `agent-*` tree at its idle limit.

The worktree must also be clean and fully pushed. No live session and no process may be inside. The lock must be gone, or its host process must be gone.

Strict is the default. A job that an older installer wrote passes no flag, so it is strict at once, with no reinstall. A person who wants the old rules passes `--attended`. The launchd plist, the Task Scheduler task and the SessionEnd hook never pass it. The agent-end reap takes no flag.

Reason: pushed proves that a copy exists. It does not prove that the work is done. The reasons for the other conditions are in `the-janitor-is-one-machine-wide-sweep`.

**Dead-rooted servers follow the same gate.** `find_dead_rooted` finds a process whose argv names a script file and whose parent directory are both gone, under a deleted checkout or worktree. It stops that process only on two reads: orphaned, and owned by the account running the sweep. It has no session read, because a deleted tree has no checkout left to hold a session. The one signal, the grace period, and the keep on an unreadable answer are the same.

**Loose processes are never stopped.** `find_loose_processes` lists a process whose argv contains a shell-snapshots path. It stops none, under any flag. That path does not prove a Claude Code Bash call started the process, or that the process is abandoned. A live session owns its own wrapper. The tier reports, and a person decides.

Kind: process
Home: janitor/test_sweep.py
