# The liveness read is platform-specific, and unreadable is not death

## The ruling

A read that can fail has three outcomes: yes, no, and "I could not tell" (`verification-report-unknown-reads`). An unreadable process read never counts as "dead". Downstream keep-or-refuse logic keeps it and never reaps it.

Why: on Windows, `ps -o lstart= -p <pid>` never answers, so every liveness read failed and read as "not live". `worktree_remove_subject` and `janitor/sweep.py`'s `decide_worktree` then read a live session's worktree as removable.

- `_process_start_ms` in `hooks/guard.py` returns three values: an int epoch millisecond (live), `None` (the pid is CONFIRMED dead), and the sentinel `PROCESS_START_UNREADABLE` (could not tell). `session_is_live` carries that as `True`, `False` and `None`.
- `worktree_live_session` answers `None` when some session's cwd sits under the target and that record's liveness read is unreadable, unless another record under the same target is confirmed live. `worktree_remove_subject` and `decide_worktree` keep-or-refuse on `None`.
- POSIX asks `ps -o lstart= -p <pid>`. Exit code 1 with empty stdout is "no such pid" (CONFIRMED dead). Any other nonzero exit, an exec failure, a timeout, or output that fails to parse is unreadable.
- Windows asks `kernel32.OpenProcess` through `ctypes`. A NULL handle with `GetLastError` 87 (`ERROR_INVALID_PARAMETER`) is CONFIRMED dead. Code 5 (`ERROR_ACCESS_DENIED`) and any other code are unreadable. A valid handle's `GetProcessTimes` creation FILETIME converts to epoch milliseconds, which needs no timezone handling. The `ctypes.windll` import lives inside the Windows-only function, never at module scope.
- `SESSION_LIVE_TOLERANCE_MS` is 60000. A session record's `startedAt` is written 1.7 to 3.2 seconds after the kernel's process-creation time on Windows.
- The tolerance is one-sided. `actual` far ahead of `started` answers `None`, not a confident `False`, because a backwards clock step and a recycled pid look the same. `started` far ahead of `actual` has no legitimate same-process reading and stays unchanged.
- `worktree_live_session` compares paths by file identity (`_path_identity`, `_under_by_identity`: `st_dev`, `st_ino`) when the strings disagree, as with a `subst` drive or a mapped network drive. When that fallback cannot tell, it answers `None`, never "outside the target".
- Cost: a recycled pid whose `startedAt` is far BEHIND the real creation time can no longer be confidently reaped. `decide_worktree` keeps the worktree, reason `unreadable-subject`. Keep is the safer trade. In `hooks/guard.py` an unreadable subject allows the git command and logs `noted`/`subject-unread`.

Proof: `worktree_live_session_two_spellings_case`, `worktree_live_session_path_unresolvable_case` and `session_is_live_backwards_clock_step_case` in `hooks/test_guard.py` drive the fallbacks at the seam, with `_path_identity` stubbed. They prove the fallback wiring, not that `os.stat` agrees on every Windows build.

## Holes, named

Debt: `liveness-windows-arm-unproven` (the Windows arm is proven only with a stubbed `ctypes.windll`, and the Windows CI job that proves it lands in a parallel change).

Kind: build
Plan: decisions/liveness-read-is-platform-specific-and-unreadable-is-not-death.md#the-ruling (all)
Home: hooks/guard.py
