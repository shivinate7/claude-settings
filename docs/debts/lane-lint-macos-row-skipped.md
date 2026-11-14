# A lane's macOS failure passes lane lint during batch CI

- **What.** While a batch `checks` run is busy, `batch-macos-skip.py` drops the macOS row from a lane's draft `lane-touched-tests` run, and the lane lint reads a missing macOS row as a pass. A lane with a macOS-only failure passes `merge --lane-lint` and the failure shows later, in the batch's own macOS run.
- **Where.** `.github/scripts/batch-macos-skip.py` and `draft_run_state` in `merge/merge.py`.
- **Decision.** `batch-macos-runner` (batch CI's macOS jobs run on the owner's Mac; its Limits list this gap); `lanes-run-no-full-ci-job` (a lane hands off only a head that passes `merge --lane-lint`).
- **Retire.** The lane lint refuses a missing macOS row when macOS tests were selected, and `merge/test_lane_lint.py` shows it.
