# A last paragraph that mixes prose and the trailer is exempt

- **What.** The guard exempts a last paragraph that mixes a prose line with the Drops-lines trailer. Git does not read such a paragraph as trailers, so the undo check refuses it. The cite then stays in the branch history.
- **Where.** `cited_record_path` in `hooks/guard.py`.
- **Decision.** `drops-lines-trailer-exempt` (a commit's Drops-lines trailer may name a record path).
- **Retire.** The guard refuses a mixed last paragraph, or the guard and the undo check agree. A case in `hooks/test_guard.py` pins it.
