# A place verb with "in <path>" for a subject's location is denied

- **What.** An Explore or Plan brief is refused when a place verb takes "in" before a path that says where the subject lives. Examples: "Generate a list of the functions in hooks/guard.py." (Explore) and "Draft a plan for the change in hooks/guard.py." (Plan). Neither asks for a file write, so both are refused wrongly.
- **Where.** `hooks/guard.py` `brief_write_hit`, the prose pass: `_brief_write_object`, which reads the first "in" after a place verb as a destination.
- **Decision.** `brief-write-needs-writer` (a read-only agent's brief never orders a file write).
- **Retire.** The reader reads "in <path>" as a destination only when the verb puts output there. Both briefs pass. "Place the report in docs/audit.md" still refuses. A case in the `brief-write-needs-writer` family in `tests/guard/s28508-rule9.py` checks each.
