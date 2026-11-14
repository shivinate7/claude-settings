# A round-2 reviewer spawned with no model runs haiku

- **What.** A reviewer brief that opens with `Round 2 of 3` and names no model passes the spawn guard and runs on the role's own model, haiku. Rounds 2 and later must run sonnet. The merge tool's `--review-record` refuses the haiku round only after the review has run (2026-11-13, lane agent-owned-processes). The harm: a wasted review and a delay.
- **Where.** `hooks/guard.py`, rule `agent-role-model`.
- **Decision.** `agent-model-cap` (the model per role, the round rows).
- **Retire.** A case in `hooks/test_guard.py` refuses a reviewer spawn whose first line carries `Round 2 of 3` or `Round 3 of 3` and names no model, with the remedy "name sonnet", and allows it with `model: sonnet`. The suite passes.
