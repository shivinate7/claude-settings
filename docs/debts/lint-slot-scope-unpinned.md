# No case pins which lints skip the lint slot

- **What.** Only `merge --lane-lint` takes a lane-lint slot. No case shows that the draft step's ready checks and the merge's own lint take none. If the slot moved into `ci_job_run`, a run that holds the merge lock would wait behind lane lints with no deadline, and its lock could expire while it waits. Whether every lane-lint case would still pass is unmeasured (no mutant run). The other side holds too: the merge's own lint takes no slot, so it runs beside as many lane lints as there are slots. How much they slow it is unmeasured.
- **Where.** `merge/merge.py` `lint_slot`, `ci_job_run`, `run_ready_checks`; `merge/test_lane_lint.py`.
- **Decision.** `merge-lock` (one run holds the merge lock for a bounded time and never waits on a lock that could expire).
- **Retire.** Add a case: with every slot held, `run_ready_checks` runs at once and prints no wait line. `merge/test_lane_lint.py`.
