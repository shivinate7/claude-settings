# A guard-touching lane lint ends unknown

- **What.** A lane lint of a change that picks a guard suite reads the guard shard steps of `checks-guard` and `checks-guard-2` as unknown, because their `NODE_PATH` expression needs `github.workspace`, which only CI sets up. The lint then ends unknown, so `merge --lane-lint` needs `--lint-unknown-ok` and the guard suites run on CI only. A guard PR proves on its CI run, not on the lane lint.
- **Where.** `bin/ci-job`, the sibling pass over other jobs of `.github/workflows/checks.yml`, and the `NODE_PATH` env of the `checks-guard` and `checks-guard-2` suite steps.
- **Decision.** `lanes-run-no-full-ci-job` (a lane runs no full CI job; the sibling pass).
- **Retire.** `ci-job` runs the guard shard steps locally, or the workflow sets `NODE_PATH` in a form it reads. A case in `lint/test_ci_job.py` shows a sibling guard step reading pass or fail, never unknown. The suite passes.
