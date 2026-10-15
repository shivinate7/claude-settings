# Plan and claude-code-guide get the general scope line

- **What.** Plan and claude-code-guide get the general scope line, which names only reviewer and Explore as never-edit. Their reader line set is right. Only the scope text is general.
- **Where.** The per-type scope text in `hooks/agent_brief.py`.
- **Decision.** `agents-get-standing-rules` (every spawned agent gets the standing rules at start).
- **Retire.** Plan and claude-code-guide each get their own scope text, and a case in `hooks/test_agent_brief.py` pins it.
