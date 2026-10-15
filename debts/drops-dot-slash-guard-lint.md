# The guard and the lint disagree on a ./deferred path

- **What.** `./deferred/a.md` after the `Drops-lines:` key passes the guard. The lint's exact match refuses it. The cost is one lint refusal and a new commit.
- **Where.** `cited_record_path` in `hooks/guard.py`, and the lint's exact match.
- **Decision.** `drops-lines-trailer-exempt` (a commit's Drops-lines trailer may name a record path).
- **Retire.** The guard and the lint give the same answer for each `./deferred/` form, and a case pins each form.
