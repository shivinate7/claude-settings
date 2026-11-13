# A long-lived branch is deleted with its merged pull request

**What.** `cut_branch` deletes the merged pull request's own origin branch. It does not read `merge.keepBranches`, so a long-lived branch merged as a pull request loses its name. Its commits stay on main. Restoring the branch is one push.

**Where.** `merge/merge.py`, `cut_branch`, called after a merge when `merge.deleteBranch` is true.

**Decision.** `merge-deletes-batch-lanes` (a merge deletes its own branch only).

**Retire.** Make the own-branch delete read `merge.keepBranches`, and keep a name listed there. Check: a fixture test with a keepBranches name that is a merged pull request's own branch. It survives the delete. Red on the current code, green after the fix.
