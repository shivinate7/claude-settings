# One guard row lets every call through when the guard is missing

- **What.** The first PreToolUse guard row in `settings.json` exits 0 when `hooks/guard.py` or python is missing, so the call runs unjudged. The second guard row exits 2 with a remedy.
- **Where.** The first PreToolUse guard row in `settings.json`.
- **Decision.** none. Parked for the owner by the arbiter at 04:50 CDT, because a fail-closed misfire during a hooks refresh would stop every session.
- **Retire.** The owner rules. If yes, the row exits 2 with the remedy of the second row. A settings test runs it with no `guard.py` and expects exit 2.
