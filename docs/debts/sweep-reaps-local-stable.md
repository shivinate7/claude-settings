# The sweep reaps a local stable branch

**What.** The sweep reaps a local `stable` on main, because its work is on the base. It reads no keep list, so `merge.keepBranches` in `.github/stamp.json`, which names `stable`, does not reach it. Sessions install from stable (plan R42 part 2), so a reaped local copy breaks them.

**Where.** `janitor/sweep.py`, `decide_branch` (the keep-or-reap rule) and `reap_branch`.

**Decision.** `none`. Related: `a-branch-is-redundant-by-patch-not-by-ancestry` (a branch whose work is on its base is reaped, which is why stable goes), and `merge-deletes-batch-lanes` (`merge.keepBranches` is the keep guard on the merge side only).

**Retire.** The sweep reads `merge.keepBranches` from `.github/stamp.json` and keeps a local branch named there. Check: `janitor/test_sweep.py` has a case where a local `stable` on an ancestor of main survives the sweep. Red on the current code, green after the fix. Close it before act 2 of the merge-flow-after-anthropic lane, since installers read stable.
