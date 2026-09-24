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

## The mechanism

`janitor/sweep.py`'s `decide_listener`, `is_orphan`, and
`is_current_user_process` hold the three reads. `processes_in` holds the
pre-check's own enumeration. `janitor/test_sweep.py`'s
`ListenerDecisionTests`, `UnreadableListenerReadTests`, and
`WorktreeProcessPreCheckTests` prove both, against real fixture processes.
