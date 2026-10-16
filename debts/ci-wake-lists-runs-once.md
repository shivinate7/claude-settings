# A later run is not judged

**What.** `ci_wake.wait_for` lists the head's CI runs again until a run that ran is judged.
A skipped draft run counts as no run. After it judges a real run, it lists no more. A later
real run is never judged. The hook can then print green while that run goes on.

**Where.** `hooks/ci_wake.py`, `wait_for`.

**Decision.** ci-wait-reads-run-status (CI waits read the run status).

**Retire.** `wait_for` lists the runs once more after each judged run. If no new run shows,
it stops. A test_ci_wake.py case adds a second real run after the first one ends. The hook
is not green until the second run ends.
