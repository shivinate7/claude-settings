# A red drop hits every suite

- **What.** `red_drop` reads the suites of every `checks` job, not the failing job's, so one red job drops each lane whose files reach any suite. Each dropped head is then refused until a new head, which voids its review record. Harm: false drops and lost throughput whenever `--drop-red` runs over two or more suite-touching lanes.
- **Where.** `merge/merge.py`, `red_drop`: it calls `hit_suites(wt, paths, set())` with no filter by job.
- **Decision.** `git-integration-branch-merge` (how lanes join a batch, and the split of a red batch).
- **Retire.** A `jobs=` filter on `hit_suites` and `checks_steps`, so `red_drop` reads only the failing jobs' suites. A case in `merge/test_merge.py` that keeps a lane whose files reach only the other job's suite, and drops one that reaches the failing job's, shows it closed.
