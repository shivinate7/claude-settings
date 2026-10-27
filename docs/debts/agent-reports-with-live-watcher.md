# An agent can report with a watcher still live

- **What.** No check stops an agent that sends its final report while a Monitor or background task it started is still running. Each agent file tells the agent to stop its tasks with TaskStop first, but nothing enforces it. A leftover watcher wakes the parent once per task end. A SubagentStop check was tried and dropped by the owner (2026-10-26): it blocked 248 of 1,787 real stops by mistake.
- **Where.** The SubagentStop path in `hooks/guard.py`. The instruction lives in each file under `agents/`.
- **Decision.** none on main. The dropped check and its draft decision, `agent-live-tasks-block-the-stop` (a live task blocks the stop), sit on branch `stop-blocks-live-tasks`, at commit b8feeb5 ("Block an agent stop that leaves a background task live").
- **Retire.** Reopen as a check only if leftover watchers keep waking parents after the agent-file instruction. A new check must show near-zero false blocks over real stops before it lands. A test with a live task at SubagentStop goes red. A test with every task stopped goes green.
