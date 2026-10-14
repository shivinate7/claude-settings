# The harness scope lint has four minor defects

- **What.** `lint/test_harness_scope.py` lines 215-217 hold the stale comment "ALL stays as it is". `STEP_FLAGS` (line 24) lacks `mods`. The pipe regex in `mods_step_problems` ignores quotes and comments, so it can misread a pipe inside a quote or comment. `.github/scripts/harness-scope.sh` line 5 is about 140 characters long.
- **Where.** `lint/test_harness_scope.py` and `.github/scripts/harness-scope.sh`.
- **Decision.** `mods-tests-run-in-gates` (mod tests run as the last step of the gates job).
- **Retire.** The comment is corrected, `mods` joins `STEP_FLAGS`, the regex skips quotes and comments, line 5 is wrapped, and a test pins each fix.
