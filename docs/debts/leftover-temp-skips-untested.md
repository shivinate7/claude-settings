# The leftover temp sweep's skip and exit paths are untested

**What.** No test covers the session-end skip, the deadline keep, or the exit 1 after a failed removal in the leftover temp-folder step. A change to any of them passes the suite.

**Where.** `janitor/sweep.py` on the head of PR 3696. In `main`: the `session_end` guard before the step, and the `failed` count that sets the exit code. In `leftover_temp_tier`: the deadline branch.

**Decision.** `leftover-temp-reap`: the leftover temp-folder reap, its skips and its exit code (leftover temp folders of dead test runs are reaped after an hour).

**Retire.** Closed when `janitor/test_sweep.py` has one case for each path: a session-end run leaves the step out; a run past its deadline keeps a folder it would reap; a failed removal makes `main` exit 1. Each case goes red when its guard is removed.
