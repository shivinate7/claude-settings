# The install lock is stale by age, and waiters can both take it

- **What.** The install lock is a file made with noclobber. A run treats a lock older than 10 minutes as dead and removes it. Two gaps follow. First, when a stale lock cannot be removed, the wait loop `continue`s before the try count or the deadline runs. It never times out. Second, two waiters can both judge the lock stale. One removes the lock the other has just made. Both then hold the lock.
- **Where.** `take_install_lock` in `install.sh`. The `CreateNew` wait loop in `install.ps1`. The noclobber wait loop in the post-merge hook text that `install.ps1` writes.
- **Decision.** `merge-reinstalls-from-main` (one lock for every installer path).
- **Retire.** Remove a stale lock only after it still shows the id that was read. End every wait at the deadline. Check: a test leaves an unremovable stale lock and expects exit at the deadline. A test races two waiters on one stale lock and expects one holder.
