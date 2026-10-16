# No check reads the trigger judgment

- **What.** Whether a change changes a guard or gate is the reviewer's reading. No check reads that call, so a wrong call skips or adds the net-value test.
- **Where.** The trigger in decision `hold-unsafe-after-round-3`, and the round-3 `Net safety value:` line in `agents/reviewer.md`.
- **Decision.** `hold-unsafe-after-round-3` (net-value hold after round 3).
- **Retire.** A check that reads the changed-file list and the reviewer's `Net safety value: n/a (checked: ...)` line, and goes red when a guard or gate file is not named.
