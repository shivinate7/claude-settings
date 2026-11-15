# The unlock DELETE has no landed check

**What.** After retry-net-method-safe, a 5xx on the lock-release DELETE stops the unlock with a network stop, and the lock stays until it expires. Before, it was retried 3 times.

**Where.** `merge/merge.py`, `GhLock.release` and `GhLock.unlock` (the DELETE of the lock ref).

**Decision.** `standing-merge-grant`, the merge tool retries a lost write only after a check that it did not land (option c).

**Retire.** Give the DELETE a `landed` check: a missing ref means done, a ref that names this run's commit means resend, another sha means never resend (a blind resend would delete another run's fresh lock). Shown closed by `merge/test_merge.py`.
