# A log row with a list or dict key stops the purge

- **What.** A log row with a list or dict `branch` or `commit`, and a live `time_ms`, raises TypeError. `realpath` has no try block. `--purge` then stops, preview included, until that row is 90 days old. Main kept such a row as unreadable. Nothing in the repo writes such a row.
- **Where.** The key build in `janitor/sweep.py`.
- **Decision.** `purge-keeps-younger-restore-ref` (the purge keeps the younger restore ref).
- **Retire.** The key build is guarded, and a case with a list or dict key keeps the row as unreadable.
