# A guard timeout or crash lets the call run

- **What.** If a PreToolUse hook times out or exits with a code other than 2, Claude Code lets the call run. The guard rows in `settings.json` set no `onFailure`, so a slow or crashed guard fails open.
- **Where.** The PreToolUse guard rows in `settings.json`.
- **Decision.** none. Parked for the owner by the arbiter at 04:50 CDT, because it changes the hook config of every session.
- **Retire.** The owner rules. If yes, the guard rows set `"onFailure": "block"` (Claude Code 2.1.295 or later), and a settings test pins it.
