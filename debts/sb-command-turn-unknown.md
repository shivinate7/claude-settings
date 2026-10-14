# Unknown whether a command prompt starts a turn in the app

- **What.** It is unknown whether a prompt sent from a command starts a turn in the app. `/safe-stop` reports "queued", and no turn starts, is an example. This is untested in the app.
- **Where.** The `$.prompt.submit` call behind `/safe-stop` in `mods/session-board`.
- **Decision.** `session-board-mod-limits` (session-board keeps small records, and /safe-stop queues one prompt).
- **Retire.** The app run shows whether the prompt starts a turn, and the result is recorded in the decision.
