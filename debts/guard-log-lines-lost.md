# A guard.log line can be lost on Windows

- **What.** A plain append from many processes is not atomic on Windows. Measured before the lock: a line was lost in 1 round of 12, each round with 20 processes calling `record`. A lost line can drop an owner note, because `collect_unread` in `hooks/decision_watch.py` names unread subjects from `noted` and `subject-unread` lines. `record()` now locks each write (msvcrt on Windows, fcntl on POSIX). It retries only on contention (BlockingIOError, errno 13, EAGAIN, EDEADLK 36), for up to `LOG_LOCK_WAIT`, 2 s. After 2 s of contention it writes without the lock. Any other lock error writes at once, without the lock. The crash path in `hooks/guard.py` (lines 253-254) also writes with no lock.
- **Where.** `record()` in `hooks/guard_core.py`, and `hooks/guard.py` lines 253-254.
- **Decision.** `guard-log-read-weekly` (guard.log is read weekly, by one reader).
- **Retire.** Every write takes the lock, or the decision records the accepted loss. The tests in `lint/test_gates.py` stay green under contention.
