# `test_no_shard_runs_all` races and is flaky

- **What.** `test_no_shard_runs_all` (test) has a race, so it is flaky. A run can fail without a code change.
- **Where.** `hooks/test_mutate_shared.py`, test `test_no_shard_runs_all`.
- **Decision.** none.
- **Retire.** A fix that removes the race and keeps the test's check. `hooks/test_mutate_shared.py` runs the test and shows it closed.
