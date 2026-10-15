# The agent brief hook has no matcher

- **What.** The SubagentStart hook has no matcher, so every agent type gets the standing rules.
- **Where.** The hook registration for `hooks/agent_brief.py` in `settings.json`.
- **Decision.** `agents-get-standing-rules` (every spawned agent gets the standing rules at start).
- **Retire.** A matcher limits the hook to the agent types that need it, or the owner records that every type gets it. A test pins the chosen rule.
