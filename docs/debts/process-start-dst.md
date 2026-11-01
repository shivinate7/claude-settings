# A process started in a repeated hour reads one hour late

**What.** `ps -o lstart=` prints local time with no zone, and `time.mktime` guesses the offset. A process started in the repeated hour of a fall-back night reads one hour late for its whole life. Batch 43 `checks-macos` went red on it (Nov 1 01:47 CDT).

**Where.** The POSIX arm of `_process_start_ms` in `hooks/git_reads.py`. Its callers are `session_is_live` and `stale_agent_lock_verdict` in `janitor/sweep.py`, which can reap a live agent's lock.

**Decision.** none

**Retire.** Read the start time with no zone guess. The fall-back cases in `hooks/test_guard.py` and `janitor/test_sweep.py` pin `TZ=America/Chicago` at Nov 1 01:30. They are red on main and green on the fix.
