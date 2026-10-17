# A repo that raises spawn depth gets no prompt to record the risk

- **What.** The rule `roles-workers-never-spawn` said a repo that needs nesting raises depth in its settings and records the risk. The rule is gone from `CLAUDE.md`. Nothing now prompts that record. The setting `env.CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` still holds depth at 1 here.
- **Where.** Deleted rule `roles-workers-never-spawn`. The setting sits in `settings.json`.
- **Decision.** `claude-md-shrink` (CLAUDE.md drops the prose of a rule that a guard or gate enforces).
- **Retire.** A check or hook asks for a risk record when a repo's settings raise the depth. Or the owner rules that no record is needed.
