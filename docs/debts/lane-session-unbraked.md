# A running lane session is not braked

**What.** The load brake reads the load on each write of an agent only (`running_lane_hit` needs an `agent_id`). A lane is a session, with no `agent_id`, so on a local session the brake reads it only at its start. A lane session that keeps writing on a full Mac is not refused.

**Where.** `hooks/guard.py` `running_lane_hit`, and decision `machine-load-brake` (the load brake), bullet "Not covered for lane sessions".

**Decision.** `machine-load-brake` (the load brake). `lanes-start-as-agents` (a lane is a session).

**Retire.** On a local session, a lane session's own write reads the load once and is refused at full. A guard test shows that refusal red before the fix and green after it.
