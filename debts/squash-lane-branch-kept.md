# A squash-merged lane is kept

**What.** A squash-merged lane has no merge commit parent. `lane_tips` reads no tip, so its branch is kept. The design does not prove that the lane landed.

**Where.** `merge/merge.py`, `lane_tips` and `cut_lanes`.

**Decision.** `merge-deletes-batch-lanes` (a merge deletes its batch's lane branches).

**Retire.** Find a proof that a squash-merged lane landed, then cut its branch. Check: a fixture test with a squash-merged lane. Its branch is cut. Red on the current code, green after the fix.
