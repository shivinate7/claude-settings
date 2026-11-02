# A Workflow agent body chosen at run time is not read

**What.** Guard rule `coordinator-scope` judges a Workflow script by the options objects it reads in each `agent()` call. A body chosen when the script runs, such as a ternary between two bodies held in variables, shows the guard no `agentType`, so a build or review agent can pass in a coordinator.

**Where.** `hooks/guard.py` (`script_agent_calls`, `coordinator_act_hit`). The guard reads text, and cannot run the script.

**Decision.** `session-tiers`, tiers and their guards (section "Spawns and merges"). Risk kind: unmeasured. No coordinator has been seen to write this form.

**Retire.** Refuse an `agent()` call whose first argument is no object literal or string literal, for a coordinator. Add a case that goes red on the old guard: a ternary between two bodies, one with a build agent type.
