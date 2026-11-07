# The Stop settle reads the transcript and every agent file when a refusal is pending

**What.** When the refusals file holds a row with a `tool_use_id`, each Stop reads the whole transcript and every `<session>/subagents/*.jsonl` file, to tell an agent's refused call from the orchestrator's. The Stop already reads the transcript for the reply, so this is an extra read of it plus one per agent. A session with many agents and a long run pays this at every Stop while a refusal waits. The cost is unmeasured.

**Where.** `lint/report_guard.py`, `tool_use_sources` through `pending_refusals`.

- **Decision.** `refusals-reach-the-owner` (refused calls reach the owner). See the agent rule and the cost section.

**Retire.** Measure the read on a real session with refusals and many agents. If it costs more than the false blocks it stops, read only the files whose agent id matches a row's `agent_id`, or stop at the first match. Closed when a test counts the files read and the decision's cost section states the measured cost.
