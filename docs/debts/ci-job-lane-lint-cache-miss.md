# A lane lint never hits the rerun cache

- **What.** `bin/ci-job` keys a saved pass on `git rev-parse HEAD`. `lane_lint` in `merge/merge.py` makes a new merge commit on each run, so the key never repeats. Each lane lint misses the cache and writes about 117 unread pass files (the review's count) into a store of 300 files.
- **Where.** `cache_key` in `bin/ci-job`, at its `git rev-parse HEAD` call. `CACHE_FILES` in `bin/ci-job`. `lane_lint` in `merge/merge.py`, whose `commit-tree` call makes the merge commit.
- **Decision.** none. Related: `lanes-run-no-full-ci-job` (a lane never runs a full CI job; it runs the lane lint). The owner's ask is under Ruling.
- **Retire.** Closed when the key holds the pushed head (`CI_JOB_HEAD_SHA`), plus HEAD's parents and message, and not HEAD's own sha. Then a second `merge --lane-lint` of the same head reads the saved pass and writes no new file. Proof: `lint/test_ci_job.py`.

## Ruling

Owner, 2026-11-19 14:31 CST: rerun only the failed checks. Lane lints were the point (owner goal item 4, 16:23 CST, 2026-11-19).
