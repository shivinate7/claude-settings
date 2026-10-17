# No check reads the spawn depth setting

- **What.** The gate row for `roles-workers-never-spawn` left with its rule. Nothing now checks that `settings.json` sets `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`.
- **Where.** `settings.json`, the `env` block.
- **Decision.** `claude-md-shrink` (CLAUDE.md drops the prose of a rule that a guard or gate enforces).
- **Retire.** A check fails when the setting is missing or above 1.
