# A fenced command or HTML line quoted for reference is denied

- **What.** A brief is refused for a fenced line that quotes a command or markup for reference. Examples: a fenced `$ python3 t.py > red.log 2>&1`, and a fenced HTML button line. The brief quotes both as reference, so both are refused wrongly.
- **Where.** `hooks/guard.py` `_brief_commands`, which reads fence lines and `$ ` lines as command text, and `_brief_write_command`, which reads a redirect target as a path.
- **Decision.** `brief-write-needs-writer` (a read-only agent's brief never orders a file write).
- **Retire.** Both fenced lines pass when the brief quotes them as reference. A fenced line that orders a write still refuses. A case in the `brief-write-needs-writer` family in `tests/guard/s28508-rule9.py` checks each.
