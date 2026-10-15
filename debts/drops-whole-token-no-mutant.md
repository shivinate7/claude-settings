# No mutant removes the whole-token match

- **What.** No mutant removes the whole-token match. The comma and semicolon cases stand in for it.
- **Where.** `hooks/mutate_guard.py` and `hooks/test_guard.py`.
- **Decision.** `drops-lines-trailer-exempt` (a commit's Drops-lines trailer may name a record path).
- **Retire.** A mutant that removes the whole-token match turns a test red.
