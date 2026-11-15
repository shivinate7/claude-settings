# A lane cycle loses the delete order

**What.** A cycle of lanes (A based on B, and B based on A) had no first lane to delete, so a failed delete could close a pull request whose base was gone. Act 4 (per-lane merge) removed the batch cut that did this. A merge now deletes only its own pull request's branch, so no cycle is cut.

**Where.** None at head. The batch cut is gone from `merge/merge.py`.

**Decision.** `merge-deletes-batch-lanes` (a merge deletes its own branch only).

**Retire.** Runnable: `merge/test_merge.py`, case `CutLanes.test_a_lane_whose_tip_the_pr_head_merged_is_kept_and_only_the_pr_branch_is_cut`, which keeps two lanes after a merge and cuts only the PR's branch. The file runs whole. A merge that cuts a lane branch reads red.
