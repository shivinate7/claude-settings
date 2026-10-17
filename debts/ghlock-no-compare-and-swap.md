# GhLock has no compare-and-swap

- **What.** The GitHub API cannot move or delete a ref "only if it is still X". `GhLock.swap` reads the ref, makes a commit, then PATCHes the ref: about 3 calls. A lock that expires between the check and the PATCH could overwrite a rival's fresh lock. The delete of an expired lock in `GhLock.acquire` has the same window, from the read of the expired lock to the DELETE. If another run breaks the lock and makes a live one inside it, the DELETE removes the live lock. Both runs then hold the lock. `GitLock` has no such window: it uses a lease.
- **Where.** `GhLock.swap` and `GhLock.acquire` in `merge/merge.py` (the `ponytail:` comments there).
- **Decision.** `merge-net-retry` (what bin/merge does on a network error or a rate limit).
- **Retire.** The GitHub backend moves and deletes the ref only while it still holds the commit it read, or a lock backend with compare-and-swap replaces it. A test with a rival that takes the lock inside the window shows the extension and the delete both stop.
