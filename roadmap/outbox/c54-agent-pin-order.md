# From the c54 thread (agent pins vs env model)

- c54: PR #714 is green and reviewed, sent to the build advisor. Update c54's status when it merges.
- New step or debt (finding, measured Oct 27): an `agents/*.md` `model:` pin beats `CLAUDE_CODE_SUBAGENT_MODEL`. So a reviewer spawn at round 2 or 3 that names no model runs Haiku, not Sonnet. Guard rule `agent-model-floor` refuses only a haiku field, and the step-up rule does not require a model field. A guard that requires `model` on a round 2 or 3 reviewer spawn would close it.
- Note (finding): a running cloud thread does not load `~/.claude/agents` files written mid-session; a fresh process does.
