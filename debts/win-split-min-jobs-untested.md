# The MIN_JOBS branch of the Windows split check has no case

- **What.** Case `test_suites_spread_over_enough_jobs` was cut. The branch that fails when fewer than `MIN_JOBS` Windows jobs carry the suites has no case. A miss costs CI wall time only. The check that each suite runs exactly once still has cases.
- **Where.** `lint/test_windows_split.py`, the `MIN_JOBS` branch.
- **Decision.** `test-strategy-reset` (cut tests that name no real failure).
- **Retire.** The wall-time cost gets a named incident, and a case then pins the branch. Or the branch is deleted.
