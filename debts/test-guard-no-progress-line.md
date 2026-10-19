# The guard test prints no progress line

- **What.** `hooks/test_guard.py` prints nothing for minutes, so the stall watch cuts off a healthy full run. Seen on 2026-10-18. The workaround is one run per `GUARD_FAMILY`.
- **Where.** `hooks/test_guard.py`, the full run with no `GUARD_FAMILY` set.
- **Decision.** `stall-watch` (a quiet tool owes a progress line at least every 120 seconds).
- **Retire.** `hooks/test_guard.py` prints a progress line at least every 120 seconds. A test shows that a background run of `python3 hooks/test_guard.py` that lasts over 300 seconds gets no STALL report.
