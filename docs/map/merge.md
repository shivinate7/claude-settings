# Merge

The tools under `merge/`. The pilot map covers one file here.

## Code files

- `merge/combine_train.py` — Folds the queued batches behind the frozen ones, in dry rounds on temporary trees, and prints the numbers of each batch. The queue is a file, or GitHub with `--from-rest`. It never pushes, never marks a pull request ready, never merges, and never changes a merge verdict, because `merge/merge.py` does not import it.
  - With `--from-rest` it lists the open pull requests, skips drafts, and orders the ready ones by number, because GitHub holds no priority. Pending ones are the in-ci batch. The first green one is next in line. The other green ones are the queued batch that folds. A red one is left out by name. An unread one is unknown and makes the exit code 2.
  - With `--from-rest` it only reads: every GitHub call is a GET, and one `git fetch` brings the heads of the queued pull requests into the checkout. A failed fetch leaves each of them unknown. It prints a `wall seconds` line for the run.
  - It reads the open pull requests and each head's CI state through the one GitHub class of the merge tool. — `uses merge/merge.py:Host`
  - It merges pairs with the one git merge wrapper of the merge tool. — `uses merge/merge.py:merge_tree`
  - It runs the fast checks through the one ci-job run of the merge tool. — `uses merge/merge.py:ci_job_run`
  - It groups the fast checks into one ci-job run per job with the merge tool's one grouping. — `uses merge/merge.py:ready_job_groups`
  - Tested by: `merge/test_combine_train.py`
