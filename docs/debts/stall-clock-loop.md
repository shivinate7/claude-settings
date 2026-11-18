# A clock loop gets no planned pause and reads as a stall at 300 s

**What.** The guard allows a clock loop in a background command, `until [ $(date +%s) -gt N ]; do sleep 30; done; cmd`, and its remedy names the form. `pause_seconds` gives that command 0, because `until` is a loop word. The watcher then reports a STALL at the base 300 s of quiet, although the loop is a planned wait. Measured 2026-11-15 17:10 CST: `pause_seconds` returns 0 for the command. Claude hits it in normal work, since the guard's remedy invites it.

**Where.** `hooks/stall_watch.py`, `pause_seconds`: its loop check returns 0 for any loop word, and its docstring calls a loop "a poll, not a wait". `hooks/guard_stream.py`, `waiter_verdict` and `clock_loop`: the allowance that lets the clock loop through. `WAITER_REASON` in the same file: the remedy that names the form.

**Decision.** stall-watch (a stalled background command is reported, never stopped).

**Retire.** A background clock loop reads as a planned pause, so its quiet limit grows by the pause. A case in `hooks/test_stall_watch.py` shows it: a clock loop in a background job gives a pause, and no STALL comes before the pause plus 300 s.
