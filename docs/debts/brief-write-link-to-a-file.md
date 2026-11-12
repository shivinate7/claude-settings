# A "to a file" that belongs to another verb is denied

- **What.** A read-only brief is refused when "to a file" belongs to another verb. Examples: "Make each finding point to a file and line." and "Record each finding with a link to the file." Both ask for the finding's content, not a file write, so both are refused wrongly.
- **Where.** `hooks/guard.py` `brief_write_hit`, the prose pass: `_brief_write_object` for "make", and the change-verb branch of `_brief_write_orders` for "record".
- **Decision.** `brief-write-needs-writer` (a read-only agent's brief never orders a file write).
- **Retire.** A "to" or "with" after a verb such as point or link is no destination. Both briefs pass. "Write the findings to docs/audit.md" still refuses. A case in the `brief-write-needs-writer` family in `tests/guard/s28508-rule9.py` checks each.
