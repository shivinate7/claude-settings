# The claude agents --json call runs on each board refresh

- **What.** `claude agents --json` runs on each board refresh. A very large session list is an example. Its cost is unmeasured.
- **Where.** The board refresh in `mods/session-board`.
- **Decision.** `session-board-mod-limits` (session-board keeps small records, and /safe-stop queues one prompt).
- **Retire.** The cost is measured on a large session list, and the number is recorded in the decision.
