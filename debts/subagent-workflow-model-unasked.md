# A write that sets the workflow subagent model is not asked

- **What.** The guard asks on a write of `CLAUDE_CODE_SUBAGENT_MODEL` or its `_FORCE` form only. So a write that sets `CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL` to `opus` is not asked.
- **Where.** `SUBAGENT_CAP_KEY` in `hooks/guard.py` (line 638), and `config_watch.py` (line 372).
- **Decision.** `subagent-model-cap` (the subagent model cap and the model per role).
- **Retire.** The guard asks on a write of `CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL` too. A test pins the ask for a write of that key set to `opus`.
