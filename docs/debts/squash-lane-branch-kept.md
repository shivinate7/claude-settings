# A squash-merged pull request keeps its local branch

**What.** `cut_local` deletes a local branch only when its tip is an ancestor of the merged head. A squash commit is not such a descendant, so the local branch of a squash-merged pull request is kept, with one line. Its origin branch is deleted. The design does not prove that the pull request landed.

**Where.** `merge/merge.py`, `cut_local`, called by `cut_branch`.

**Decision.** `merge-deletes-batch-lanes` (a merge deletes its own branch only).

**Retire.** Find a proof that a squash-merged pull request landed, then cut its local branch. Check: a fixture test with a squash-merged pull request. Its local branch is cut. Red on the current code, green after the fix.
