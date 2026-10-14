# A line in the harness scope script is about 140 characters

- **What.** `.github/scripts/harness-scope.sh` line 5 is about 140 characters long.
- **Where.** `.github/scripts/harness-scope.sh`, line 5.
- **Decision.** `mods-tests-run-in-gates` (mod tests run as the last step of the gates job).
- **Retire.** Line 5 is wrapped to a readable length.
