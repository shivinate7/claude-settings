# Sessions loaded another way may not show on the board

- **What.** The store is per plugin and per config folder. Sessions loaded another way, or under another config folder, do not show. A `--plugin-dir` run writes `session-board_inline-<hash>.json`. The host names the file. Whether the app and the terminal share one store is unknown.
- **Where.** The store path in `mods/session-board`.
- **Decision.** `session-board-mod-limits` (session-board keeps small records, and /safe-stop queues one prompt).
- **Retire.** The app and the terminal are checked for a shared store, and a case with `--plugin-dir` shows its sessions.
