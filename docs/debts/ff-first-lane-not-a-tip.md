# A fast-forwarded first lane is no tip

**What.** The old tip reader read merge commits only, so a lane that fast-forwarded onto the base had its tip unread and its branch never cut. Act 4 (per-lane merge) removed that reader and the batch cut. No lane branch is cut now, so nothing reads a lane's tip.

**Where.** None at head.

**Decision.** `merge-deletes-batch-lanes` (a merge deletes its own branch only).

**Retire.** Runnable: `merge/test_lane_fast_forward.py`, which is not written yet. It holds a case whose PR head fast-forwards onto the base and brings in a lane: the lane's branch stays on origin and the PR's own branch is cut. Until that file is tracked and green, no check runs, so a close is held.
