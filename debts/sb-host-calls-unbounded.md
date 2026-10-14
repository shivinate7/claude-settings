# Some session-board host calls are not bounded by the 100 ms wait

- **What.** The 100 ms wait does not bound every host call. At session start, `$.session.repo()` and `$.command.register()` are awaited with no bound. At session end, the store deletes are unbounded. On clear or resume, `$.session.repo()` is unbounded too. A slow store delete that holds the session end is an example. The cost is unmeasured.
- **Where.** The session start, session end and clear or resume handlers in `mods/session-board`.
- **Decision.** `session-board-mod-limits` (session-board keeps small records, and /safe-stop queues one prompt).
- **Retire.** Each host call sits under a bound, and a case with a slow store delete finishes inside it.
