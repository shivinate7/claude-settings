# A check-in made before the crossing does not clear the block

**What.** `checked_in` counts a check-in only when it was made at or after the agent's crossing of 30 minutes (`when >= crossed`). So a good pending check-in made before the crossing does not clear the block. Reviewer probe: a 31-minute agent with a `send_later` made at minute 29 with delay 30 still blocks the Stop. The cost is one extra turn per agent. Case A13b uses no delay, so it does not separate a pending check-in from one that has fired.

**Where.** `hooks/stall_watch.py`, `checked_in` (the `when >= crossed` test, :1222), called from `read_job` in `stop()` (:1305).

**Decision.** stall-watch (a stalled background command is reported, never stopped).

**Retire.** A case in `hooks/test_stall_watch_stop.py` with a check-in made before the crossing, set to fire after it, that names the agent: the Stop prints no block, and the case passes.
