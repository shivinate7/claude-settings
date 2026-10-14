# The purge confirm total counts kept refs

- **What.** The "purge: N" total in the confirm report counts rows whose ref was kept. The total then counts more than the refs dropped.
- **Where.** The confirm report in `janitor/sweep.py`.
- **Decision.** `purge-keeps-younger-restore-ref` (the purge keeps the younger restore ref).
- **Retire.** The total counts only the refs dropped, and a case pins the count.
