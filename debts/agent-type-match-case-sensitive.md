# The agent type match is case-sensitive

- **What.** `Builder` or `explore` gets the general writer scope, not the scope of its role.
- **Where.** The type match in `hooks/agent_brief.py`.
- **Decision.** `agents-get-standing-rules` (every spawned agent gets the standing rules at start).
- **Retire.** The match ignores case, and a case in `hooks/test_agent_brief.py` pins `Builder` and `explore` to their role's scope.
