# Question for the owner: should a guard timeout refuse the call?

- **What.** If the PreToolUse guard times out or crashes, Claude Code lets the call run. The owner chose this in `gate-hooks-fail-closed`, so load never takes the setup down. The cost is that a slow or crashed guard judges nothing.
- **Where.** The PreToolUse guard row in `settings.json`, which sets no `onFailure`.
- **Decision.** `gate-hooks-fail-closed` (a missing gate refuses; a slow or crashed gate does not).
- **Retire.** The owner keeps the ruling, and this file is deleted. Or the owner changes it, the guard row sets `"onFailure": "block"`, and a settings test pins it.
