# The harness scope lint has a stale comment

- **What.** `lint/test_harness_scope.py` lines 215-217 hold the stale comment "ALL stays as it is".
- **Where.** `lint/test_harness_scope.py`, lines 215-217.
- **Decision.** `mods-tests-run-in-gates` (mod tests run as the last step of the gates job).
- **Retire.** The comment is corrected to match the code.
