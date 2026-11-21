# Merge

The tools under `merge/`. The pilot map covers one file here.

## Code files

- `merge/combine_train.py` — Folds the queued batches of a queue file behind the frozen ones, in dry rounds on temporary trees, and prints the numbers of each batch. It never pushes, never marks a pull request ready, never merges, and never changes a merge verdict, because `merge/merge.py` does not import it. With `--build --name NAME` and no `--queue`, the members come from `merge.reviewed_read`'s `batch` rows, kept only when the pull's base is main, and the lowest-numbered row left is the front PR, which merges alone. With `--build --name NAME` it builds the local integration branch from a backlog of queued members (the `BUILD_THRESHOLD` constant), as one no-ff merge each onto the newest main, and prints the pull request body. It pushes nothing. A member whose live head moved, or that clashes, leaves by name. Under the threshold it prints `merge alone`, builds nothing and exits with its own code. `--build` with `--lint` is refused.
  - It merges pairs with the one git merge wrapper of the merge tool. — `uses merge/merge.py:merge_tree`
  - It runs the fast checks through the one ci-job run of the merge tool. — `uses merge/merge.py:ci_job_run`
  - It groups the fast checks into one ci-job run per job with the merge tool's one grouping. — `uses merge/merge.py:ready_job_groups`
  - It names the build branch with the merge tool's one integration branch form. — `uses merge/merge.py:integration_branch`
  - It prints the body of the integration pull request with the merge tool's one freeze block writer. — `uses merge/merge.py:freeze_lines`
  - Tested by: `merge/test_combine_train.py`
