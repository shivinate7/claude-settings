# Lane model recheck

- **What.** Lane sessions run Sonnet for now. Waiting-page item 439 (lane-model-sonnet, 2026-11-08 12:21 CST, pick none) set it temporarily. The measure behind it: lane token-spend-sources (12:16 CST) counted 13 lanes at $4 to $40 each, about $18 on average, with 58 to 74 percent of tokens on Opus. Recheck the cost per lane session against the ~$18 Opus average, and each lane that stalled or asked for Opus. Due 2026-11-22.
- **Where.** `docs/decisions/agent-model-cap.md`, the `lane session` row of the model table. `docs/decisions/session-tiers.md`, Lane session model.
- **Decision.** `agent-model-cap` (agent model cap, the model per role).
- **Retire.** Closed when the owner rules on the lane model from the recheck, with the figures recorded in the decision's Measured part. That ruling rewrites the lane row and `session-tiers`' Lane session model in place, then this file is deleted.
