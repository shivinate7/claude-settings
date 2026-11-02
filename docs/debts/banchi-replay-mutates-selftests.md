# A banchi replay mutates self-test scripts as product code

- **What.** The banchi Python code pattern reads `scripts/*-selftest.py` as product code, so a replay mutates self-test code. 7 of the 23 banchi Python survivors sit in three such files: `scripts/pricearchive-selftest.py` 3, `scripts/slabs-store-selftest.py` 2, `scripts/slabs-routes-selftest.py` 2.
- **Where.** `REPLAY_PROFILES["banchi"]["parts"]["py"]` in `hooks/mutate_guard.py`: its `code` pattern.
- **Decision.** `mutation-report-scores-suites` (the mutation report scores suites).
- **Retire.** Exclude `scripts/.*-selftest\.py$` from the banchi Python `code` pattern. A replay fixture in `hooks/test_mutate_replay.py` shows that no mutant lands in a `-selftest.py` file.
