# The round-order rule does not judge a workflow reviewer

**What.** Rule `review-rounds-in-order` reads Agent and Task spawns only. A workflow agent with `agentType: 'reviewer'` and a `Round 2 of 3` brief passes while the first round's reviewer still runs. A workflow fan-out of review rounds can repeat the PR 2038 incident. Found by review round 1 of PR 2158, 2026-11-08.

**Where.** `hooks/guard.py` `round_order_hit`.

**Decision.** review-rounds-in-order (a later review round waits for the earlier round's reviewer).

**Retire.** Read the agents a Workflow script spawns, as the spawn rules read them, and judge each reviewer agent. Add a case to family review-rounds in `hooks/test_guard.py` for a workflow `Round 2 of 3` reviewer beside a running first round.
