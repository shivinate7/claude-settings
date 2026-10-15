# The Windows slice run hides most skipped guard cases

- **What.** Nine guard cases skip on Windows: 2 subject, 6 kill and 1 simulator. They are not in the Windows slice, so a Windows PR run prints only one SKIP row. A reader cannot see that the nine cases did not run.
- **Where.** The `skip_case` rows and `WINDOWS_CHECKERS` in `hooks/test_guard.py`.
- **Decision.** `test-strategy-reset` (tests prove outcomes and never fail on runner speed).
- **Retire.** A Windows slice run prints one SKIP row for each case that skips on Windows.
