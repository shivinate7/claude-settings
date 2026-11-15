# Merge

The tools under `merge/`. The pilot map covers one file here.

## Code files

- `merge/combine_train.py` — Folds the queued batches of a queue file behind the frozen ones, in dry rounds on temporary trees, and prints the numbers of each batch. It never pushes, never marks a pull request ready, never merges, and never changes a merge verdict, because `merge/merge.py` does not import it.
  - It merges pairs with the one git merge wrapper of the merge tool. — `uses merge/merge.py:merge_tree`
  - It runs the fast checks through the one ci-job run of the merge tool. — `uses merge/merge.py:ci_job_run`
  - It groups the fast checks into one ci-job run per job with the merge tool's one grouping. — `uses merge/merge.py:ready_job_groups`
  - Tested by: `merge/test_combine_train.py`
