# The purge key compares branch names with exact case

- **What.** Branch names compare with exact case, but NTFS ref names fold case. An expired `Foo` row and an unexpired `foo` row at one commit drop the shared ref. Main dropped it too. The real log has 0 case collisions.
- **Where.** The purge key build in `janitor/sweep.py`.
- **Decision.** `purge-keeps-younger-restore-ref` (the purge keeps the younger restore ref).
- **Retire.** The key lower-cases the branch, and a case with `Foo` and `foo` at one commit keeps the ref.
