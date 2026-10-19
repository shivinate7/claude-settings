# A fast-forwarded first lane is no tip

**What.** `lane_tips` reads merge commits only. A lane that fast-forwards onto the base has no merge commit. Its tip is never read, so its branch is never cut. 0 of 112 recent lane merges did this.

**Where.** `merge/merge.py`, `lane_tips`.

**Decision.** `merge-deletes-batch-lanes` (a merge deletes its batch's lane branches).

**Retire.** Read the tip of a fast-forwarded lane too. Check: a fixture test whose first lane fast-forwards. Its branch is cut. Red on the current code, green after the fix.
