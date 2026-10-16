# The install lock is removed with no id check

- **What.** The install lock file holds its holder's id. The EXIT trap in `install.sh` removes the lock with no id check. The EXIT trap in the post-merge hook text does the same. A run can outlive the 10-minute stale age. A later run then takes the lock as stale. When the old run exits, its trap removes that later holder's lock. A third run can then overlap it. Severity: low. It needs a run that lasts past 10 minutes.
- **Where.** `finish_install` in `install.sh` (the EXIT trap, about line 239). The EXIT trap in the post-merge hook text that `install.ps1` writes.
- **Decision.** `merge-reinstalls-from-main` (one install lock for every installer path).
- **Retire.** Each EXIT trap checks the lock id first. Check: a test ends a run after a second run takes the lock. The second lock stays. The stale path sits in `install-lock-stale-by-age`, and one id check may close both.
