# The session-board pane draw is untested in the desktop app

- **What.** The pane draw is untested in the desktop app. A press on a row does not open its detail view is an example. Only the app or a terminal draws the pane.
- **Where.** The `/board` pane draw in `mods/session-board`.
- **Decision.** `session-board-mod-limits` (session-board keeps small records, and /safe-stop queues one prompt).
- **Retire.** The pane is run in the desktop app, and the result is recorded in the decision.
