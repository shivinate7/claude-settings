# The review stamp cutover stops at depth 50

**What.** In a depth-50 cloud clone, `review_stamp_since` stops once main is more than 50 commits past the stamp commit. The salt commit is outside the shallow history, so the report guard's Stamp check gives only the UNKNOWN note. Unmeasured: whether the cloud allows `git fetch --unshallow origin`.

**Where.** `merge/merge.py`, `review_stamp_since` and `tool_stamp_since`, whose Stop says the checkout lacks the review stamp salt.

**Decision.** `pr-review-record` (a pull request carries its review record on the PR).

**Retire.** PR #2242 (review-cutover-shallow-deepen) fixes it by deepening the clone. Closed when that PR merges and `merge/test_merge.py` passes on its head.
