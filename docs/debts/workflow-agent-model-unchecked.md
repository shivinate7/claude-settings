# Workflow agents skip the role model check

- **What.** Guard rule agent-role-model checks Agent and Task spawns only. A workflow script's `agent()` call can name a model above its role's row, and nothing refuses it. An Explore `agent()` on sonnet with no `Audit:` marker on its brief's first non-blank line is one such call.
- **Where.** The Agent and Task match in `hooks/guard.py` (rule agent-role-model); the Workflow tool's script. `role_model_check` returns at once for any tool outside `SPAWN_TOOLS`. Claude hits it when it writes a workflow.
- **Decision.** `agent-model-cap` (the model-per-role table), whose workflow row says a workflow agent follows the role table.
- **Retire.** The guard reads each `agent()` call's role and model in a Workflow script. A case shows a workflow builder on opus refused. A case shows an Explore `agent()` on sonnet with no `Audit:` marker refused. The Workflow scan (`script_agent_calls`) feeds each readable `agent()` call through `role_model_check`.
