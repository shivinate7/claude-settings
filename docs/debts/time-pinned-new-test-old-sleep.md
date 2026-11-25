# A new test that calls an old sleeping helper passes --check --base

- **What.** `--check --base` fails only on a finding whose own line the branch adds. A `sleep` in a helper that the branch does not touch is not on an added line. A new test that calls the helper adds no finding line, so the check passes, though the test waits on a fixed sleep.
- **Where.** `lint/find_time_pinned.py`, `report_new_only`: `new` keeps only the findings whose line `added_lines` reports. The CI step "Time-pinned new-finding check" (`.github/workflows/checks.yml`) runs it.
- **Decision.** `test-strategy-reset` (point 2: no timed wait on a fixed sleep).
- **Retire.** `lint/test_find_time_pinned.py` has a case where a new test calls an old sleeping helper, and `--check --base` exits 1 on it.
