# The guard's records header is an unpinned copy

- **What.** `RECORDS_HEADER` in `hooks/guard_merge.py` is a copy of the first line of `RECORDS_INTRO` in `lint/hook_catalog.py`. No test compares them (rule `building-allow-list-is-the-constant`, a gate points at the constant, never a copy). If the intro title changes, the guard stops matching the generated page. It then lets each lane commit of the page pass, with no sign.
- **Where.** `hooks/guard_merge.py`, `RECORDS_HEADER`. The source is `RECORDS_INTRO` in `lint/hook_catalog.py`.
- **Decision.** `records-index-at-merge` (one records index page, rebuilt at merge time). Its "Holes, named" section names this gap.
- **Retire.** A pin test asserts `RECORDS_INTRO.startswith(RECORDS_HEADER)`. It shows red when one string changes alone, and green when both match.
