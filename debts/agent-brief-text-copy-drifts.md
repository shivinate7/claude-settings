# The agent brief text can drift from the rules it copies

- **What.** The SubagentStart hook's rule text is a copy of the rules in CLAUDE.md and `agents/*.md`. A rule change needs a second edit, and the test pins the copy, not the source.
- **Where.** `hooks/agent_brief.py` (rule text) and `hooks/test_agent_brief.py`.
- **Decision.** `agents-get-standing-rules` (every spawned agent gets the standing rules at start).
- **Retire.** A check reads the rules in CLAUDE.md and `agents/*.md`, and goes red when the hook text differs from them.
