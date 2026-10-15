# Long rate-limit waits can outlast the lock TTL spare

- **What.** Every `GhLock` call retries a rate limit up to 3 times with a 60 s wait, so one call can wait 180 s. Several rate-limited steps in one run, plus the checks wait, can pass the lock's TTL. A checks pass makes about 4 `gh` calls, each up to 180 s, so one pass can take 12 minutes, past the 600 s spare. `confirm` never reads the lock again before the merge. A checks pass makes about 4 `gh` calls, each up to 180 s, so one pass can take 12 minutes, past the 600 s spare. `confirm` never reads the lock again before the merge. The lock then expires while the run still holds it, and a second run can take it.
- **Where.** `GhLock.api`, `wait_checks`, `confirm` and the lock TTL in `merge/merge.py`.
- **Decision.** `merge-net-retry` (the merge tool retries a network error or a rate limit, then stops).
- **Retire.** The run renews or re-checks its lock after a rate wait, or the TTL covers the worst wait. A test with three rate-limited steps and a short TTL shows the lock still held.
