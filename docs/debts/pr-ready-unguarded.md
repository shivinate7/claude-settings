# Nothing guards marking a PR ready

- **What.** The `draft-pr` guard rule reads only the create command and the MCP create tool. A lane PR can go ready, or go ready before review.
- **Where.** `hooks/guard.py`, the `draft-pr` guard rule.
- **Decision.** `claude-md-shrink` (CLAUDE.md drops the prose of a rule that a guard or gate enforces).
- **Retire.** A guard asks before a PR that is not an integration PR goes ready.
