# A lease branch can be removed by archive-then-delete

**What.** Until the merge tool's lost-work list skips lease branches, a coordinator's archive-then-delete of a branch with no merge base can remove a lease branch, which lifts the lease.

**Where.** `merge/merge.py`, the lost-work list: state f, the `lost-work branch NAME (f)` rows of `merge --reviewed --live FILE`.

**Decision.** lease (the lease tool and its owner rulings: a lease is a `lease/NAME` branch on the remote).

**Retire.** The lost-work list skips `lease/` branches. A case in `merge/test_lost_work.py` shows that a lease branch with no merge base is not listed as lost work.
