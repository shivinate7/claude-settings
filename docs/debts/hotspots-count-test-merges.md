# Test-merge refs are counted as merges

**What.** The replay counts GitHub test-merge commits (refs such as `origin/pr3911m`). Each one duplicates a real PR merge, and it is counted because its second parent later landed on the base. The run of 2026-11-25 on base 1d2738e0e counted 6 of them: 757 replayed, 87 conflicted, 11.5%. Without them: 751 replayed, 87 conflicted, 11.6%. The conflicted count and the per-file counts do not change, so only the total and the rate are inflated.

**Where.** `lint/conflict_hotspots.py`, `merges_since` at :140, the `elif` that keeps a merge whose second parent is on the base.

**Decision.** none

**Retire.** Walk only refs that are branches or main, or drop a merge whose tree equals a later merge on the base. A case in `lint/test_conflict_hotspots.py`, red first on the current code: a fixture with a test-merge ref whose tree matches a later base merge replays once, not twice.
