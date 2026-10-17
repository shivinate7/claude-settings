# A workflow that GitHub has not created yet reads as green

- **What.** The merge wait reads the checks and the workflow runs of the head, and reads again after a settle pause. A workflow that GitHub creates after that last read is not seen. The head then reads as green without it.
- **Where.** `wait_checks` in `merge/merge.py`, the settle read (`SETTLE_SECONDS`).
- **Decision.** `merge-waits-on-every-check` (the merge waits on every check, before and after the claim).
- **Retire.** The wait knows which workflows the head must have, and holds until each has a run. A test where a workflow appears after the settle pause shows the wait still held.
