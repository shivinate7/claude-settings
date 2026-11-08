# A late run is not judged

**What.** `ci_wake.wait_for` lists the head's CI runs once more, at once, after the first judged run, and judges
any run that shows there. Its runs go ahead of the runs judged before, so a newer run of a name outranks the older
one. A refused re-list keeps the runs already judged. A run that first shows after that re-list is not judged. The hook can then print green
while that run goes on.

**Where.** `hooks/ci_wake.py`, `wait_for`.

**Decision.** ci-wait-reads-run-status (CI waits read the run status).

**Retire.** Keep listing after the re-list, each list 30 s or more after the one before, until a list shows no
new run. A test_ci_wake.py case shows a run first listed after the at-once re-list, and the hook is not green
until it ends.
