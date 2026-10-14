# An edit to the guard log reader selects extra CI

- **What.** An edit to `lint/guard_log_report.py` selects `gates_windows_merge` and the `guard` suite, as well as `code`. Neither reads guard.log, so the cost is CI time. The macOS and Windows runs of the `decision_watch` tests also select on this edit.
- **Where.** The scope step of `.github/workflows/gates.yml`.
- **Decision.** `guard-log-read-weekly` (guard.log is read weekly, by one reader).
- **Retire.** An edit to the reader selects only `code`, and a scope test pins the selection.
