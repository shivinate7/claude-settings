# The stall message repeats at every Stop

- **What.** There is no dedupe. The message fires at every Stop while a job stays open.
- **Where.** The Stop path in `hooks/stall_watch.py`.
- **Decision.** `stall-watch` (the stall watch flags open jobs at Stop).
- **Retire.** Report each job ID once. A test with two Stops and one open job gives one message.
