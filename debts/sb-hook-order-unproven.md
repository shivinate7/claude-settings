# The host hook order for the permission check is unproven

- **What.** The host hook order is untested. The mod assumes that the host runs the permission check inside `next()`. A permission label that outlasts its tool call is an example. A headless run did not confirm the order.
- **Where.** The permission check in `mods/session-board`.
- **Decision.** `session-board-mod-limits` (session-board keeps small records, and /safe-stop queues one prompt).
- **Retire.** The app run confirms the order, or the mod stops relying on it.
