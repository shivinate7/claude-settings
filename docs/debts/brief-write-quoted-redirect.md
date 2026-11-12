# A quoted redirect example in a brief is denied

- **What.** A backticked redirect quoted as an example is refused as an order, e.g. "Round 1 FAILED on a false alarm: `echo x > out.txt` was refused." Two of 12 real read-only briefs from one session were denied, both wrongly.
- **Where.** `hooks/guard.py` `brief_write_hit`, the command pass (`_brief_commands`).
- **Decision.** `brief-write-needs-writer` (a read-only agent's brief never orders a file write).
- **Retire.** Quoted text after "e.g.", "was refused", "denies" or "refused" is data, not an order, even in backticks. A case in the `brief-write-needs-writer` family in `hooks/test_guard.py` checks it.
