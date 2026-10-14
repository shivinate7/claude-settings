# No run shows the Stop message reaches the model

- **What.** No run shows that a Stop systemMessage reaches the model. The alarm may never reach the model. `decision_watch` uses the same channel.
- **Where.** The Stop systemMessage in `hooks/stall_watch.py`.
- **Decision.** `stall-watch-stop-check` (the stall watch flags open jobs at Stop).
- **Retire.** In a live session, leave a job open at Stop. The model receives the message, and the run is recorded.
