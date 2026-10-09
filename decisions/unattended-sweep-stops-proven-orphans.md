# Unattended sweep stops proven orphans

PR #132 added an orphaned-listener check to `janitor/sweep.py`. The
SessionEnd hook and the scheduled task both call that sweep with
`--confirm`, unattended. This entry records the owner's choice for that
path, and the pre-check rule measured alongside it.

## What an unattended run can stop

A `--confirm` run, run by the SessionEnd hook or the scheduled task, can
send one signal to one process. All of these must be true first:

- The process is orphaned. The read is per-OS. It answers three states,
  never two: orphaned, not orphaned, or unreadable.
- No live Claude session has a cwd in the same checkout.
  `guard.worktree_live_session` is the oracle. This sweep never re-derives
  that answer.
- The process is owned by the account running the sweep.

The signal is SIGTERM on Linux and macOS. It is `TerminateProcess` on
Windows. Both go by pid, never by a name or a pattern. The sweep never
sends a second, stronger signal on its own.

## The decision

A stopped process cannot come back. A reaped branch keeps a tombstone. A
kept worktree stays whole. A stopped process has neither.

The owner still chose, on 2026-09-24, to let both unattended paths stop a
proven orphan with no separate arm flag. The code in PR #132 already does
this. The owner's word keeps it as it stands.

PR #132 raised a manual-only flag as an open question. That flag would
have required a person to pass `--confirm` by hand, every time, for this
one new capability. The owner decided against that gate. The three reads
above are the gate.

## Scope: every checkout, not only worktrees and scratch-workspaces

On 2026-09-24 the owner was told what "everywhere" can mean. A `nohup` dev
server in a PRIMARY checkout, left running after its terminal closed, can
be orphaned too. The owner's own Banchi server can be orphaned the same
way, if it runs from its own checkout with no Claude session open there.
Either one can be stopped, the same as a listener left behind in a
worktree.

Two narrower options were offered instead:

- Cover linked worktrees and scratch-workspaces only. Leave a primary
  checkout alone.
- Cover every checkout, but only behind a manual flag. Drop the
  unattended paths.

The owner kept "everywhere," with no new flag and no narrower scope. The
three reads in this entry are still the whole gate. A primary checkout
gets no separate exemption.

## What reopens it, added

A stopped process the owner started ON PURPOSE also reopens this. That
process must still answer the three reads above as a real orphan, with no
session open in its checkout. A report that this happened to a process
the owner meant to keep running is the same reopen trigger already named,
not a new one.

## The pre-check rule, measured alongside this

`decide_worktree`'s own pre-removal check asks whether any process sits
inside a worktree, before that worktree is removed. An early version kept
the worktree whenever even one process's cwd could not be read.

MEASURED on a real Windows machine, 2026-09-24. 272 of 580 running
processes failed that one read. Most belonged to another account. Some
were otherwise access-protected. Keeping on any one of those would have
refused to reap anything, anywhere, on any real machine.

A single process whose cwd cannot be read is out of scope now. It never
blocks a removal. Only the WHOLE pid enumeration failing still means
keep-everything.

This matches the direction already named for the owner check. A process
this sweep cannot read is out of scope. It is counted. It is never acted
on. It is never a reason to keep something else.

## What reopens it

Any report of a stopped process that was not a true orphan reopens this.
That includes a false "no live session" answer. It also includes a false
"orphaned" answer, or a false "owned by the current user" answer. Each
one traces back to a real process an unattended run should not have
touched.

## An unattended run may remove a worktree

Owner ruling, 2026-10-01: every `--confirm` run, the daily job and SessionEnd
included, needs both of these to remove a worktree:

- Merged, or pushed and idle 24 hours. Merged means HEAD holds no commit that
  the default branch lacks. The test is the redundancy test of
  `a-branch-is-redundant-by-patch-not-by-ancestry.md`, by ancestry or by
  patch, read in the worktree. A detached HEAD counts by its commit. A pushed
  tree has every commit on a remote branch. It is removed once it is idle 24
  hours, merged or not (owner ruling, 2026-10-09). The remote keeps every
  commit. Before that, the keep reason is `unmerged`.
  Incident, 2026-10-09: q_max held 138 worktrees, each with a live Neon branch.
  73 were detached checkouts whose commits were on a remote, kept only for
  `unmerged`.
- Idle 1 hour. Read the newest mtime of the worktree's own `index`, `HEAD`
  and `logs/HEAD`, under `.git/worktrees/<name>`. It must be 60 minutes old.
  The sweep reads it before any `git status`, which can rewrite the index. A
  younger tree is kept, and the reason is `recently-active`. A time that
  cannot be read keeps the tree, and the reason is `unreadable-subject`.

The old conditions stay. The worktree must be clean and fully pushed. No live
session and no process may be inside. The lock must be gone, or its host
process must be gone.

Strict is the default. A job that an older installer wrote passes no flag, so
it is strict at once, with no reinstall. A stale installed job fails safe. A
person who wants the old rules passes `--attended`. The launchd plist, the
Task Scheduler task and the SessionEnd hook never pass it. The agent-end reap
stops processes and removes no worktree, so it needs no flag.

Why: the 03:17 daily run on 2026-10-01 removed q_max's live wave 15
integration worktree (`w15-port`). It was clean and pushed, but not merged,
and in use (`launchd-sweep.log`, line 2799). Pushed proves that a copy exists.
It does not prove that the work is done. The reasons for the old conditions
are in `the-janitor-is-one-machine-wide-sweep.md`.

The mechanism: `janitor/sweep.py`'s `decide_worktree`, `_strict_keep` and
`worktree_idle_seconds`. `janitor/test_sweep.py`'s `StrictWorktreeTests`
proves them. `janitor/mutate_sweep.py` carries 15 mutants for them.

## Dead-rooted servers follow the same gate

`find_dead_rooted` finds a process whose argv names a script file and whose
parent directory are both gone, under a deleted checkout or worktree. It stops that process
only on two reads: orphaned, and owned by the account running the sweep. It
reuses `is_orphan`, `is_current_user_process`, and `reap_listener`. It has no
session read, because a deleted tree has no checkout left to hold a session.
The one signal, the grace period, and the keep on an unreadable answer are the
same. A report of a stopped process that was not a true orphan reopens this
tier too.

## Loose processes are never stopped

`find_loose_processes` lists a process whose argv contains a shell-snapshots
path. It stops none, under any flag. The argv containing that path does not
prove a Claude Code Bash call started the process, and does not prove the
process is abandoned. A live session owns its own wrapper. No read here
proves an orphan that no live session claims. The tier reports, and a person
decides.

## The mechanism

`janitor/sweep.py`'s `decide_listener`, `find_dead_rooted`, `is_orphan`, and
`is_current_user_process` hold the reads. `processes_in` holds the
pre-check's own enumeration. `janitor/test_sweep.py`'s
`ListenerDecisionTests`, `UnreadableListenerReadTests`,
`WorktreeProcessPreCheckTests`, `DeadRootedServerTests`, and `LooseProcessTests` prove them, against
real fixture processes.
