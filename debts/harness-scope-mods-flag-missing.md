# The harness scope lint lacks the mods step flag

- **What.** `STEP_FLAGS` (line 24 of `lint/test_harness_scope.py`) lacks `mods`.
- **Where.** `STEP_FLAGS` in `lint/test_harness_scope.py`.
- **Decision.** `mods-tests-run-in-gates` (mod tests run as the last step of the gates job).
- **Retire.** `mods` joins `STEP_FLAGS`, and a test pins the flag.
