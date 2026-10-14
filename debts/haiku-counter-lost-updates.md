# Parallel calls lose counter updates

- **What.** Heavy parallel calls of one session lose counter updates. A measured stress of 4 threads by 300 calls ended at 30 of 1200. The loss errs toward judging. Real Stops of one session come seconds apart.
- **Where.** The counter update in the Stop reply judge hook.
- **Decision.** `haiku-prompt-hooks` (haiku prompt hooks, Stop reply judge).
- **Retire.** Serialize the counter write, or count under a lock. The same stress run ends at 1200 of 1200.
