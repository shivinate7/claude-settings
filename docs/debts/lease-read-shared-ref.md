# Lease reads in one clone share a local ref

**What.** Each lease read in one clone, and in that repo's worktrees, fetches into the same local ref `refs/lease-read/NAME`, and each read force-updates it. Two readers at once can lose git's ref lock. The read then retries the fetch once. If the retry fails too, the read is UNKNOWN, which refuses; it fails closed. Measured 2026-11-25 on the lease PR (number 3883), head commit 0c02a7465e, with readers in one clone and the ref moving: 2 readers, 0 of 80 reads failed; 4 readers, 1 of 160; 8 readers with 2 movers, 18 of 160. With the ref stable: 0 of 240. Claude is likely to hit it once guards read the lease on each guarded act, since a session and its agents share one clone.

**Where.** `hooks/lease.py`, `read`: the fetch into `refs/lease-read/NAME` and its one retry (`FETCH_TRIES`).

**Decision.** lease (the lease tool and its owner rulings: a lease is a `lease/NAME` branch on the remote).

**Retire.** A read that shares no local ref: a ref name per process, or a read that stores no ref. Build it before or with the first guard that reads the lease, in the step `lease-proof`. Its case goes in `hooks/test_lease.py`: two reads at once, the ref moving, and no read UNKNOWN.
