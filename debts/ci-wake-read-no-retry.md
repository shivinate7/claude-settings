# A failed read is not retried

**What.** One failed status read ends a CI-wake wait as unknown, with no retry. The test
stub also models only `in_progress`, so a wait that stops early at a `queued` run is not
caught. Neither gap can read green.

**Where.** `hooks/ci_wake.py`, `watch_run`; the stub in `hooks/test_ci_wake.py`.

**Decision.** ci-wait-reads-run-status (CI waits read the run status).

**Retire.** A failed read gets one retry after the 30 s pause. The stub can show `queued`,
and a case shows the wait keeps reading past it.
