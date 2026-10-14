# The lock's expiry read has no retry

- **What.** The merge lock reads its commit message once, with no retry. A server error there gives an endless expiry, so `acquire` refuses with "never expires" on a network blip.
- **Where.** The lock commit-message read in `merge/merge.py`, near the `GhLock` expiry parse.
- **Decision.** `merge-net-retry` (a network error retries, a proven refusal reverts).
- **Retire.** That read goes through the same retry as `GhLock.read`. A test with one failed read, then a good one, gets the real expiry.
