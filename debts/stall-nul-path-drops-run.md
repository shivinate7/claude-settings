# A NUL byte in a path drops the whole run

- **What.** `os.stat` raises ValueError on a path with a NUL byte, and the check does not catch it. Every row for that run drops. Paths written by the harness cannot reach this.
- **Where.** The `os.stat` call in `hooks/stall_watch.py`.
- **Decision.** `stall-watch-stop-check` (the stall watch flags open jobs at Stop).
- **Retire.** Catch ValueError for each row, so one bad path drops one row. A test with a NUL path keeps the other rows.
