# A slash word after "as" or "called" is read as a path

- **What.** A read-only brief is refused when a slash word follows "as" or "called". Examples: "Write the verdict as approve/reject." and "Write each finding as hooks/guard.py:123 plus a reason." The first names a value, and the second a file and line as a format. Neither is a destination, so both are refused wrongly.
- **Where.** `hooks/guard.py` `_brief_write_path` (the slash rule), reached through `_brief_write_object`, where "as" and "called" are in `BRIEF_WRITE_DEST`.
- **Decision.** `brief-write-needs-writer` (a read-only agent's brief never orders a file write).
- **Retire.** Both briefs pass. "Write the report as docs/audit.md" still refuses, since a path after "as" is a destination. A case in the `brief-write-needs-writer` family in `tests/guard/s28508-rule9.py` checks each.
