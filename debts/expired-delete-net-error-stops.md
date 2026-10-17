# A network error on the expired-lock delete stops the run

- **What.** The delete of an expired lock in `GhLock.acquire` runs once. It has no retry and no wait, so a late retry cannot remove another run's fresh lock. A network error or a rate limit on it now stops the run with NetStop. Before, the delete retried.
- **Where.** `GhLock.acquire` in `merge/merge.py`.
- **Decision.** `merge-net-retry` (what bin/merge does on a network error or a rate limit).
- **Retire.** The delete is conditional on the lock it read (debt `ghlock-no-compare-and-swap`), so a retry is safe. A test with one network error on the delete shows the run goes on.
