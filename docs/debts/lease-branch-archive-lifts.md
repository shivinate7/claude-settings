# A lease branch can be removed by archive-then-delete

**What.** `merge/merge.py` `lost_work_branches` does not skip `lease/` branches. A lease branch with no merge base is listed as lost work once it is 6 hours old (`merge/merge.py` `LOST_WORK_DONE_HOURS`) and no pull request holds it. Until the list skips lease branches, a coordinator's archive-then-delete of a listed branch can remove a lease branch, which lifts the lease.

**Where.** `merge/merge.py` `lost_work_branches` (the list) and `merge/merge.py` `lost_work_rows` (state f: the `lost-work branch NAME (f)` rows of `merge --reviewed --live FILE`).

**Decision.** lease (the lease tool and its owner rulings: a lease is a `lease/NAME` branch on the remote).

**Retire.** Closed when `merge/merge.py` `lost_work_branches` skips `lease/` branches, and a case in `merge/test_lost_work.py` shows that a lease branch with no merge base is not listed as lost work. Neither is built.
