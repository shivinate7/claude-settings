# Workflow agents skip the role model check

- **What.** Guard rule agent-role-model checks Agent and Task spawns only. A workflow script's `agent()` call can name a model above its role's row, and nothing refuses it.
- **Where.** The Agent and Task match in `hooks/guard.py` (rule agent-role-model); the Workflow tool's script.
- **Decision.** `agent-model-cap` (the model-per-role table), whose workflow row says a workflow agent follows the role table.
- **Retire.** The guard reads each `agent()` call's role and model in a Workflow script, and a case shows a workflow builder on opus refused.
