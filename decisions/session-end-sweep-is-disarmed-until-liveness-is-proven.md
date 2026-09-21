# The SessionEnd sweep is disarmed until liveness is proven on Windows

The `SessionEnd` hook is removed from `settings.json`. It stays removed until
the two conditions below are both true. This entry records why, and what
re-arms it.

## The defect

`hooks/guard.py` reads a process start time with `ps -o lstart= -p <pid>`. That
read is the whole liveness oracle. On Windows the `ps` command in this
environment has no `-o` option, so the read always fails. A failed read returns
`None`, and `session_is_live` turns `None` into `False`. Every session on the
machine then reads as dead.

MEASURED on Windows 11, 2026-09-21: this session's own record (pid 42972, cwd
the pointer checkout) read `live=False` while the session was running.

## Why that makes the hook unsafe

`janitor/session_end_sweep.py` runs `janitor/sweep.py <root> --confirm`. That
call reaps for real. It is not a preview.

`janitor/sweep.py` keeps a worktree when `guard.worktree_live_session` answers
true. With the oracle blind, that answer is always false. The guarantee in
`plans/janitor-build-plan.md`, "The sweep never removes a worktree that a live
session stands in", does not hold on Windows.

MEASURED the same day: a preview over `~/Clones` named three worktrees in
`job-cost-reporting` as removable, with no live-session test behind that
answer.

The loss is bounded. A dirty worktree is still kept, and a reaped branch keeps
a tombstone for 90 days. The working directory is the unbounded part. A live
session standing in a reaped worktree loses its own cwd in the middle of a
turn.

## The decision

Remove the `SessionEnd` hook from `settings.json`, on every platform, not on
Windows alone. The owner named the act on 2026-09-21.

Every platform, because the same file installs on every machine. A platform
test inside the config would state the rule in the one place that cannot test
it. The macOS behaviour is correct today, so this disarm costs a working sweep
there. That cost is accepted for the days the fix takes.

## What re-arms it

Both of these, together:

1. The liveness read answers three states, not two: alive, dead, and
   unreadable. An unreadable read reaches the caller as `None`, which both
   callers already treat as keep-or-refuse. A live session on Windows reads
   live.
2. A Windows job in `.github/workflows/gates.yml` runs the guard and sweep
   suites, and passes.

Condition 1 fixes the defect. Condition 2 is what makes a check go red on it
the next time. One without the other leaves this platform unproven.

## The mechanism

`hooks/session_start.sh` prints a notice at the top of every session while the
`SessionEnd` hook is absent from `settings.json`. The notice names this entry.
The check reads the config, so it stops on its own the day the hook returns. It
does not read a date or a flag that a person must clear by hand.

The notice answers three states, never two. Present is silence. Absent is the
disarm notice. A config that cannot be read at all is reported as unknown,
which is the contract `lint/check_unknown_reads_contract.py` states.

MEASURED against both arms on 2026-09-21. The notice printed once against a
config with no `SessionEnd` hook. It printed nothing against that same config
with the hook put back.

This entry is the fallback. The notice is the enforcement.
