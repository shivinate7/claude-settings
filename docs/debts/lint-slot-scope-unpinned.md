# No case pins which lints skip the lint slot

- **What.** Only `merge --lane-lint` takes a lane-lint slot. No case shows that the draft step's ready checks and the merge's own lint take none. Moving the slot into `ci_job_run` passes every lane-lint case, and then a run that holds the merge lock can wait behind lane lints until the lock expires.
- **Where.** `merge/merge.py` `lint_slot`, `ci_job_run`, `run_ready_checks`; `merge/test_lane_lint.py`.
- **Decision.** `merge-lock` (one run holds the merge lock for a bounded time and never waits on a lock that could expire).
- **Retire.** Add a case: with every slot held, `run_ready_checks` runs at once and prints no wait line. `merge/test_lane_lint.py`.
