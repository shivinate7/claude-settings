# A long-lived head is lost in a batch

**What.** `cut_lanes` deletes any origin head whose sha is a lane tip. Only `merge.keepBranches` keeps such a head. A long-lived branch merged into a batch loses its name. Its commits stay on main. Restoring the branch is one push.

**Where.** `merge/merge.py`, `cut_lanes`.

**Decision.** `merge-deletes-batch-lanes` (a merge deletes its batch's lane branches).

**Retire.** Find a rule that tells a lane of this batch from a long-lived branch at the same tip, and keep the long-lived one. Check: a fixture test with a long-lived branch at a lane tip. It survives the cut. Red on the current code, green after the fix.
