# The purge keeps a ref that no log entry names

- **What.** The purge keeps a ref when no log entry names its commit. Such a ref is kept forever. The old code dropped it at 90 days.
- **Where.** The keep rule in `janitor/sweep.py`.
- **Decision.** `purge-keeps-younger-restore-ref` (the purge keeps the younger restore ref).
- **Retire.** The orphan rule is decided, and a case pins the outcome for an orphan ref at 90 days.
