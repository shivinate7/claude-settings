# A turn that ends during a prompt has an unknown state

- **What.** The permission signal is a tool check that returns "ask". Turn end during a prompt is unknown. A turn that ends while a prompt is still open is an example. Headless mode cannot test it.
- **Where.** The permission check and the turn-end handler in `mods/session-board`.
- **Decision.** `session-board-mod-limits` (session-board keeps small records, and /safe-stop queues one prompt).
- **Retire.** The app run shows the state at turn end during a prompt, and a case pins it.
