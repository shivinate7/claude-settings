# The batch route's local budget is below the checks job's CI cap

**What.** The batch route's local budget, `BATCH_SECONDS` (3600 s), is below the `checks` job's CI cap (75 min, 4500 s). A batch-route timeout reads unknown, and `--lint-unknown-ok` never lifts it. Each Retire check runs before the batch checks, up to 1800 s each, outside `BATCH_SECONDS`. So the batch route's total can pass the 7200 s background timeout that the batch runner sets. Wall time is unmeasured.

**Where.** `merge/merge.py`: `BATCH_SECONDS` in the batch route of `lane_lint` (`debt_check`, then `batch_run`). `.github/workflows/checks.yml`: job `checks`, `timeout-minutes: 75`. `lint/check_debt_retire.py`: `TIMEOUT`, 1800 s per suite.

**Decision.** `lanes-run-no-full-ci-job` (a lane runs no full CI job; the batch form and its budget).

**Retire.** Close it when the batch route's local bounds hold the `checks` job's CI cap, and its whole run, Retire checks included, fits under the 7200 s background timeout. `merge/test_lane_lint.py` shows it closed, with a case that reads both bounds.
