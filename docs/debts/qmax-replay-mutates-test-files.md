# q_max replay mutates test files

- **What.** The q_max profile reads `harness/browser/*.test.mjs` as product code. Its `code_not` excludes only `harness/tests/`, so a replay mutates test code by mistake. 20 of the 51 q_max survivors sit in one such file, `harness/browser/verify.test.mjs`.
- **Where.** `REPLAY_PROFILES["q_max"]` in `hooks/mutate_guard.py`: its `code` and `code_not` patterns.
- **Decision.** `mutation-report-scores-suites` (the mutation report scores suites).
- **Retire.** Exclude test files from the q_max `code` pattern. A replay fixture in `hooks/test_mutate_replay.py` shows that no mutant lands in a `*.test.mjs` file.
