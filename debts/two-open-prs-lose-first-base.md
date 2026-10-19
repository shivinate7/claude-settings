# Two open PRs lose the first base

**What.** `Host.open_heads` sets the first row's base to None when a second open PR has the same head name. A stacked PR on a same-batch lane can then be closed, depending on row order.

**Where.** `merge/merge.py`, `Host.open_heads`.

**Decision.** `merge-deletes-batch-lanes` (a merge deletes its batch's lane branches).

**Retire.** Keep the bases of a head's open PRs as a set. Check: a test with two open PRs on one head, both bases kept, in both row orders. Red on the current code, green after the fix.
