# A slow git read leaves a repo unknown for minutes

- **What.** A quick git read resets the back-off. A repo whose read takes over 5 s stays unknown. A status read of 6 s is an example. Reads then run up to 5 minutes apart, and the row reads unknown. A larger cap is unmeasured.
- **Where.** The back-off timer in `mods/session-board`.
- **Decision.** `session-board-mod-limits` (session-board keeps small records, and /safe-stop queues one prompt).
- **Retire.** The read time is measured on large repos, and the cap is set from the numbers.
