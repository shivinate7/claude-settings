# A session id with a pipe or backtick breaks the log table

- **What.** A `|` in a session id splits its cell in the `--by-session` table. Control characters are stripped, so an id cannot add a line. A backtick is not stripped, so it could close the fence in the verbatim `other` rows. The fault is display only: counts use the raw id.
- **Where.** The `--by-session` table in `lint/guard_log_report.py`.
- **Decision.** `guard-log-read-weekly` (guard.log is read weekly, by one reader).
- **Retire.** The table escapes a pipe and a backtick in each cell, and a case with each id renders one whole table.
