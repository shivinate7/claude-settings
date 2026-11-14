# The merge lock's TTL is sized for waits that are gone

**What.** `confirm` takes the merge lock for `(WAITS * deadlineMinutes + 10) * 60` seconds. `WAITS` counts three check waits under the lock, and the cutover removed them. A crashed confirm now holds the lock for the whole sized span. The `WAITS` comment still names `host.wait_checks`, which is gone.

**Where.** `merge/merge.py`, the `WAITS` constant and its use in `confirm` (the `lock.acquire` call).

**Decision.** `merge-lock` (the merge lock: one merge at a time, and its expiry).

**Retire.** Size the TTL from the work that remains, with no `WAITS` constant. Check: a case in `merge/test_merge.py` that pins the TTL of a confirm with no wait. Red on the current code, green after the fix.
