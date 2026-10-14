# The purge runs realpath once per unexpired row

- **What.** `realpath` runs once per unexpired row, in preview too. A dry run on a copy of the real log took 1.35 s, against 0.015 s before. A first call to an unreachable network host took 1.15 s.
- **Where.** The key build in `janitor/sweep.py`.
- **Decision.** `purge-keeps-younger-restore-ref` (the purge keeps the younger restore ref).
- **Retire.** The key builds lazily or is cached per repo string. A timing case pins the dry-run cost.
