# The expired-lock delete can retry for minutes and ignores its result

- **What.** When `GhLock.acquire` finds an expired lock, it deletes it. That delete now retries through rate waits, up to 180 s. In that window another run can renew or take the lock, and the delete then removes a live lock. The result of the delete is ignored, so a rate limit that outlasts the retries reads as Held.
- **Where.** `GhLock.acquire` in `merge/merge.py`.
- **Decision.** `merge-net-retry` (the merge tool retries a network error or a rate limit, then stops).
- **Retire.** The delete is conditional on the lock it read, or it is not retried. A failed delete stops with its own line. A test pins each case.
