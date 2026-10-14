# Long rate-limit waits can outlast the lock TTL spare

- **What.** Every `GhLock` call retries a rate limit up to 3 times with a 60 s wait, so one call can wait 180 s. Several rate-limited steps in one run, plus the checks wait, can pass the lock's TTL. The lock then expires while the run still holds it, and a second run can take it.
- **Where.** `GhLock.api` and the lock TTL in `merge/merge.py`.
- **Decision.** `shared-merge-tool` (the merge lock rules; the plan holds the lock TTL, no decision entry names it yet).
- **Retire.** The run renews or re-checks its lock after a rate wait, or the TTL covers the worst wait. A test with three rate-limited steps and a short TTL shows the lock still held.
