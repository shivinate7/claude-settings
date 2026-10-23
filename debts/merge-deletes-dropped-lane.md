# The merge tool deletes a dropped lane's branch

**What.** After a batch merges, the merge tool deletes the remote branch of every lane merged into the batch, including a lane the batch later reverted. Batch #564 (goal-1 batch) lost five such branches on 2026-10-23. They were restored by hand at the tips the tool printed. A dropped lane needs its branch to rejoin.

**Where.** `merge/merge.py`, the lane cleanup after a merge (the `deleted at` line).

**Decision.** git-integration-branch-merge (rule in `CLAUDE.md`: batch lanes, drop a red lane, fix it in its own lane).

**Retire.** The tool keeps a lane branch whose merge into the batch was reverted on the batch. A test: a batch with one lane merged and then reverted, merged; that lane's branch still exists.
