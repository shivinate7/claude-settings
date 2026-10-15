# An auto-approve mode can answer an ask with no person present

- **What.** An auto-approve mode can answer an "ask" with no person present. The mod cannot tell this apart. A "permission" label that shows during a call no person answers is an example. The mod has no mode check.
- **Where.** The permission check in `mods/session-board`.
- **Decision.** `session-board-mod-limits` (session-board keeps small records, and /safe-stop queues one prompt).
- **Retire.** The mod reads the permission mode, and a case pins the label under auto-approve.
