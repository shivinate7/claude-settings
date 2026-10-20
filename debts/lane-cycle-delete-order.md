# A lane cycle loses the delete order

**What.** `cut_lanes` deletes dependents first. In a cycle of lanes (A based on B, and B based on A), no lane is first, so it deletes in heads order. A failed delete in the cycle can then close a PR whose base is gone.

**Where.** `merge/merge.py`, `cut_lanes`, the delete order.

**Decision.** `merge-deletes-batch-lanes` (a merge deletes its batch's lane branches).

**Retire.** Keep every lane of a cycle, with a line. Check: a fixture test with two lanes based on each other. Both are kept. Red on the current code, green after the fix.
