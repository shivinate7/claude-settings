# A list under a "Do not:" heading is denied

- **What.** A read-only brief is refused when its prohibition heading has no run verb after the negator. Examples: "Do not:" over "- Write the findings to docs/audit.md", and "You must not:" over "  * create a file". The list prohibits the order, so both are refused wrongly.
- **Where.** `hooks/guard.py` `_brief_heading`, which needs a run verb within two words after the negator, and `_brief_commands`, which gives a list the heading's cover.
- **Decision.** `brief-write-needs-writer` (a read-only agent's brief never orders a file write).
- **Retire.** A negating heading covers the items under it with or without a run verb. "Do not:" and "You must not:" over a list pass. A case in the `brief-write-needs-writer` family in `tests/guard/s28508-rule9.py` checks each form.
