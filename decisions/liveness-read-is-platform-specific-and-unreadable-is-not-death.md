# The liveness read is platform-specific, and unreadable is not death

`hooks/guard.py`'s liveness oracle (`_process_start_ms`, `session_is_live`,
`worktree_live_session`) folded two different facts into one answer. "The
process is dead" and "the read itself failed" both came back as `None` or
`False`. No decision in this repository named a platform for this read
before now. This one does.

## What was measured

On Windows, `ps -o lstart= -p <pid>` never answers `-o` at all. Every call to
`_process_start_ms` failed, on every pid, on every session. `session_is_live`
read that failure as `False`, "not live." `worktree_live_session` and
`worktree_remove_subject` then read a live session's worktree as removable.
`janitor/sweep.py`'s `decide_worktree` would have reaped it. This is a real
defect on Windows, not a hypothetical one. The same read runs on every
platform this repository ships CI for.

## The principle

A read that can fail has three outcomes, not two: yes, no, and "I could not
tell." Collapsing the third into the second is a silent, wrong answer dressed
as a confident one. CLAUDE.md's Verification paragraph already states this
for a different subject: "report a read that could not run as unknown, never
as clear or broken." This decision applies that same rule to process
liveness.

An unreadable process read must never count as "dead." It is a third,
distinct outcome. Downstream keep-or-refuse logic must treat it the way it
already treats an unreadable session directory. Keep it. Never reap it.

## The fix

`_process_start_ms` now returns three distinguishable values. An int epoch
millisecond means that the process is live. `None` means that the pid is
CONFIRMED dead. The module-level sentinel `PROCESS_START_UNREADABLE` means
that the read could not tell either way. `session_is_live` carries that split through as `True`,
`False`, and `None`. `worktree_live_session` no longer folds an unreadable
record's own liveness read into "not live" by a bare `continue`. It answers
`None` when some session's cwd sits under the target and that record's own
liveness read is unreadable. The exception: another record under the same
target is confirmed live, and that record wins.

Both existing consumers already kept-or-refused on a `None` from
`worktree_live_session` before this change: `worktree_remove_subject` in
`hooks/guard.py`, and `decide_worktree` in `janitor/sweep.py`. Neither
needed to change. They already had the right shape for a third state. Only
the oracle feeding them was folding that state away before it ever reached
them.

## The read itself is platform-specific

POSIX asks `ps -o lstart= -p <pid>`. `ps` answers exit code 1 with empty
stdout for "no such pid," the CONFIRMED dead case. Any other nonzero exit
code is unreadable, never death. So is an exec failure, a timeout, or output
that fails to parse.

Windows asks `kernel32.OpenProcess` directly, through `ctypes`. A NULL
handle with `GetLastError` code 87 (`ERROR_INVALID_PARAMETER`) means that no
such process exists, the same CONFIRMED dead case. Code 5
(`ERROR_ACCESS_DENIED`) means that the process exists but this read cannot
see into it. That is unreadable. Any other code is also unreadable. A valid
handle's `GetProcessTimes` creation FILETIME converts straight to epoch
milliseconds. It needs no timezone handling at all. FILETIME is UTC-anchored
by definition. `ps -o lstart=` prints local time with no zone marker, and it
already carried its own documented UTC-parsing trap.

The `ctypes.windll`/`ctypes.wintypes` import for the Windows arm lives
inside the Windows-only function, never at module scope. A Linux run of this
guard never touches an import that raises there.

## Tolerance widened alongside this fix

`SESSION_LIVE_TOLERANCE_MS` moved from 5000 to 60000. MEASURED: on Windows, a
session record's `startedAt` is written 1.7 to 3.2 seconds after the
kernel's own process-creation time. A correct read can fall outside a
5-second window under load. That misreads a live session as a recycled pid.

## Holes, named

This repository has no Windows machine to run the Windows arm on. The arm's
own branching logic is proven with a stubbed `ctypes.windll` in
`hooks/test_guard.py`, not with a real kernel32 call. That covers error 87
versus error 5 versus a valid handle. A green Windows CI job is still the
read that proves this arm against the real platform. That job lands in a
parallel change to this same Windows-parity sequence.
