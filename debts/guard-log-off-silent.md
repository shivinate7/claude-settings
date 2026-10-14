# guard.log logging is disabled with no marker

- **What.** A missing `hooks/guard_core.py`, or an older one without `set_log_session`, disables STE logging. No marker line is written. The reader then prints empty tables, which read as no events.
- **Where.** The STE logging path through `guard_logger` in `lint/_transcript.py`, and `record` in `hooks/guard_core.py`.
- **Decision.** `guard-log-read-weekly` (guard.log is read weekly, by one reader).
- **Retire.** Disabled logging writes one marker line, and the reader prints a warning instead of empty tables. A test pins both.
