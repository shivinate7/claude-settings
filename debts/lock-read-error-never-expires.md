# A failed lock-commit read gives a lock that never expires

- **What.** When `GhLock.read` cannot read the lock commit for a reason that is not a network or rate error, it returns an expiry of infinity. That lock then never expires, and every later run reads it as held.
- **Where.** `GhLock.read` in `merge/merge.py`.
- **Decision.** `merge-net-retry` (the merge tool retries a network error or a rate limit, then stops).
- **Retire.** An unreadable lock commit stops the run with a clear line. A test pins it.
