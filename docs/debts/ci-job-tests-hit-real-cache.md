# Two suites write into the real ci-job pass store

- **What.** `BatchLintFlags.lane_lint` and `ci_job_case` run the real `bin/ci-job` without `XDG_CACHE_HOME` or `CI_JOB_NO_CACHE`. Each run writes 3 or 4 files into the real pass folder, `~/.cache/claude-settings/ci-job-pass` when `XDG_CACHE_HOME` is unset. Each run also evicts saved passes that real runs need.
- **Where.** `merge/test_lane_lint.py`, `BatchLintFlags.lane_lint` (about lines 3449 to 3457). `actions/ste-lint/test_action.py`, `ci_job_case` (about lines 1355 to 1365).
- **Decision.** none.
- **Retire.** Set `CI_JOB_NO_CACHE=1`, or a temporary `XDG_CACHE_HOME`, in both suites. Closed when a run of both leaves the real pass folder's file count unchanged. Proof: `merge/test_lane_lint.py` and `actions/ste-lint/test_action.py`.
