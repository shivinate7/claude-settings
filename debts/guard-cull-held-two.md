# Two guard rules held for the Mac guard.log count

- **What.** `gh-api-method` and `ln-over-directory` have zero guard.log lines on this Windows machine (20,685 lines since 2026-09-16), yet they stay. The count covers Windows only. `gh-api-method` guards the API route to merges and settings changes. `ln-over-directory` can do real harm only on Mac.
- **Where.** Both rules in `hooks/guard.py`, their rows in `hooks/test_guard.py`, their mutants in `hooks/mutate_guard.py`.
- **Decision.** `cull-rules` (how a cull of rules, guards, tests and records runs). Owner ruling 2026-10-22 02:44 CDT, batch 8.
- **Retire.** Count the Mac guard.log with `lint/guard_log_report.py --all-rules --days all` (lands with the l1 lane). Cull each rule whose count is zero on both machines, with its code, tests and mutant. Keep a rule with a Mac count above zero. Delete this file when both are decided.

## Ruling

Owner, 2026-10-22 02:44 CDT: hold both until the Mac guard.log is counted. Cull them on both machines' counts.
