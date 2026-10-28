# Make round 2 and 3 reviewers run Sonnet (c142, a reviewer at round 2 or 3 runs Sonnet)

Resumed Oct 28, lane session on branch c142-reviewer-sonnet, from claude-settings main e0f9e2d.

Pick: (a), the guard asks for the model. Why: (b) moves agents/reviewer.md to Sonnet, so round 1 runs
Sonnet unless each spawn names haiku. That breaks the table row "reviewer | haiku" in decision
agent-model-cap (the model-per-role table), a ruling only shiv changes. (a) matches the table.

Stale premise in the brief: "nothing catches a missing field" is false for the Agent and Task tools.
Guard rule roles-third-try-steps-up (step_up_hit, hooks/guard.py) already denies a reviewer spawn with
a `Round 2 of 3` line and no sonnet model; test "reviewer Round 2 of 3 with no model is denied" is on
main 6a3e842 and e0f9e2d. Probed Oct 28: denied.
Real gap, probed Oct 28 on e0f9e2d: a Workflow `agent("Round 2 of 3 ...", {agentType: "reviewer"})`
with no model is allowed and runs the Haiku pin. Recorded as notes line step-up-plugin-types
("a Workflow agent() call is not checked"). This lane extends the step-up to Workflow agent() calls.
Out of scope, left as notes: prose forms ("Review round 2"), plugin role types, model via a variable.

Status: builder (opus) dispatched: red test, then the fix.
