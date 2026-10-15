# The harness pipe regex ignores quotes and comments

- **What.** The pipe regex in `mods_step_problems` ignores quotes and comments. It can misread a pipe inside a quote or a comment.
- **Where.** `mods_step_problems` in `lint/test_harness_scope.py`.
- **Decision.** `mods-tests-run-in-gates` (mod tests run as the last step of the gates job).
- **Retire.** The regex skips quotes and comments. A test pins a pipe inside a quote, and a pipe inside a comment.
