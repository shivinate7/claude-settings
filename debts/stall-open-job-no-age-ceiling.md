# An old open job reads as still running

- **What.** Open jobs have no age ceiling. A job left from a resumed session reads as still running.
- **Where.** The open-job list in `hooks/stall_watch.py`.
- **Decision.** `stall-watch-stop-check` (the stall watch flags open jobs at Stop).
- **Retire.** Add an age ceiling past which an open job does not alarm. A test with an old job gives no alarm.
