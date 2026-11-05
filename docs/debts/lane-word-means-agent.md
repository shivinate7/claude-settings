# Some text still calls an agent a lane

**What.** The owner ruled that a lane is a session, local and cloud alike (decision `lanes-start-as-agents`). Some text still calls an agent a lane. A reader can start a lane as an agent.

**Where.** Skill `design-explore` ("each lane is one designer agent", and its `Lane kind:` header). Agent file `designer`. Decision `lanes-start-in-tool-worktrees` ("lane agents"). Decision `the-janitor-is-one-machine-wide-sweep` ("lane worktree"). Decision `machine-load-brake` (the load brake), where its busy and full bullets still say lane. The busy refusal text, `running_lane_hit` and its comment that cites the old heading "Running lanes", in `hooks/guard.py`. The decision slug `lanes-start-as-agents` itself, which names the old meaning. The `Lane kind:` header is read by `hooks/test_blind_brief.py`, so its rename is a guard lane.

**Decision.** `lanes-start-as-agents` (a lane is a session).

**Retire.** A grep of `docs/`, `skills/`, `agents/` and `hooks/` finds no text that calls an agent a lane. The renamed brief header passes `hooks/test_blind_brief.py`.
