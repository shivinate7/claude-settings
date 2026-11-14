# A kill of merge leaves ci-job running

**What.** A SIGTERM, SIGHUP or SIGKILL to the merge process alone leaves ci-job running in its own session. Its steps die at 300 s each, so at most (number of steps) x 300 s of step time; ci-job's start-up and wrap-up have no bound once merge is gone. Before PR 3423, a kill of merge's process group reached ci-job.

**Where.** `merge/merge.py`: the `--ready` and `--fast-checks` dispatch in `main`, which is outside `release_on_signals`. Also `ci_job_run`, which starts ci-job in its own session.

**Decision.** `lanes-run-no-full-ci-job` (a lane runs no full CI job; the ready checks).

**Retire.** Closed when `merge/test_ready_kill_group.py` shows that killing merge ends ci-job and its steps. The closing PR adds that file.
