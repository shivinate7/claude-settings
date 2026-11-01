# role-model-workflow-explore

**What.** A Workflow `agent()` call that sets `agentType: 'Explore'` and `model: 'sonnet'` with no `Audit:` first line passes the Explore marker rule. Only `Agent` and `Task` spawns are read.

**Where.** `role_model_check` in `hooks/guard.py`, rule `agent-role-model`, which returns at once for any tool outside `SPAWN_TOOLS`. Claude hits it when it writes a workflow.

**Decision.** `agent-model-cap`, the model per role.

**Retire.** The Workflow scan (`script_agent_calls`) feeds each readable `agent()` call through `role_model_check`, with a guard test that refuses an unmarked Explore on sonnet in a script.
