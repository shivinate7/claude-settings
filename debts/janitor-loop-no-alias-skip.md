# bin/claude-janitor has no alias skip

- **What.** `bin/claude-janitor` keeps the old loop with no skip. It is a user command, not a hook.
- **Where.** `bin/claude-janitor`.
- **Decision.** `gate-hooks-fail-closed` (a gate whose script or python is missing refuses the call).
- **Retire.** `bin/claude-janitor` skips the `/WindowsApps/` alias, and a test pins it.
