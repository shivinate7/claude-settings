# Rate-wait time is not in the lock's TTL budget

- **What.** A rate wait moves the lock's expiry to now + wait + 300 s, and only when that is later than the expiry. The lock's TTL budget (each checks wait once, plus ten minutes spare) does not grow by the time the wait used. The checks waits that follow can pass the expiry. `confirm` never reads the lock again before the merge. Only `LOCK_MAX_HOLD` (6 h from the take) bounds a long hold. Review finding F2.
- **Where.** `Lock.extend_for`, `confirm`, `LOCK_MARGIN` and `LOCK_MAX_HOLD` in `merge/merge.py`.
- **Decision.** `merge-net-retry` (what bin/merge does on a network error or a rate limit).
- **Retire.** A rate wait adds its time to the lock's budget, or the run extends the lock before each checks wait. A test with a rate wait followed by a checks wait that would pass the old expiry shows the lock still held.
