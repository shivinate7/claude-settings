# A quoted redirect example in a brief is denied

- **What.** A backticked redirect quoted as an example is refused as an order, e.g. "Round 1 FAILED on a false alarm: `echo x > out.txt` was refused." Two of 12 real read-only briefs from one session were denied, both wrongly. A backticked prose order quoted as data is refused the same way, e.g. "Check that `Write the findings to docs/audit.md` is refused by the reader."
- **Where.** `hooks/guard.py` `brief_write_hit`, the command pass (`_brief_commands`) and the prose pass.
- **Decision.** `brief-write-needs-writer` (a read-only agent's brief never orders a file write).
- **Retire.** Quoted text after "e.g.", "was refused", "denies" or "refused" is data, not an order, even in backticks. That holds for a redirect and for a prose order, such as one after "Check that". A case in the `brief-write-needs-writer` family in `tests/guard/s28508-rule9.py` checks it.
