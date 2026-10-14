# A closed stdout pipe ends the STE gate with no log line

- **What.** If the reader closes stdout early, the STE gate raises at its flush in `answer()`, before the log call. Measured on Windows: `OSError` Errno 22, 21 stderr lines, exit 120, and no log line. On POSIX the error is `BrokenPipeError`, not measured. `md_sweep` catches the same error in its own try, not measured. The exit code is unchanged. A closed pipe means that the host has already gone.
- **Where.** `answer()` in the STE gate.
- **Decision.** `guard-log-read-weekly` (guard.log is read weekly, by one reader).
- **Retire.** The POSIX error is measured, and a test writes the log line before the flush. Or the decision records the exit code as accepted.
