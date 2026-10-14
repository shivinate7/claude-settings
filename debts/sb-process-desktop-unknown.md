# The $.process call is CLI only in the session-board notes

- **What.** The API notes `$.process` as CLI only. If it fails in the desktop app, no session reads ready, and the `claude agents` seed is missing. The board then shows store entries alone.
- **Where.** The `$.process` calls in `mods/session-board`.
- **Decision.** `session-board-mod-limits` (session-board keeps small records, and /safe-stop queues one prompt).
- **Retire.** The `$.process` call is tested in the desktop app, and the result is recorded in the decision.
