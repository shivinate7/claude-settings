# A later run is not judged

**What.** `ci_wake.wait_for` lists the head's CI runs once. A run that starts after that
list is never judged, so the hook can print green while that run goes on.

**Where.** `hooks/ci_wake.py`, `wait_for`.

**Decision.** ci-wait-reads-run-status (CI waits read the run status).

**Retire.** `wait_for` lists the runs again after each judged run. It stops when no new run shows.
A test_ci_wake.py case adds a run after the first list and is not green until it ends.
