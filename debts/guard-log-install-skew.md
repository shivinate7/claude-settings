# A mixed guard_core and decision_watch install drops notes

- **What.** A new `hooks/guard_core.py` writes six fields. An old `hooks/decision_watch.py` skips each line whose field count is not five. It then drops every unread note. `install.sh` lands both files from one source, so only a partial copy, such as a Windows file copy, splits them. Also, `record` reads `_log_session` with `globals().get`. A stale `guard_core.py` therefore writes its old five fields. The test `session_log_stale_core_case` proves the code path, not the real skew.
- **Where.** `record` in `hooks/guard_core.py`, and the field count in `hooks/decision_watch.py`.
- **Decision.** `guard-log-read-weekly` (guard.log is read weekly, by one reader).
- **Retire.** A test runs a real stale core against the new reader. It uses no stub. The reader accepts both field counts.
