# Old counter files are not removed

- **What.** No code purges `state/`. One file of at most 70 bytes stays per session.
- **Where.** The counter state folder for the Stop reply judge.
- **Decision.** `haiku-prompt-hooks` (haiku prompt hooks, Stop reply judge).
- **Retire.** Purge counter files past a set age. A test with an old file shows its removal.
