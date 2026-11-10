# The orchestrator rule is guarded for one tier only

**What.** `lint/rule_mechanisms.json` marks rule `roles-orchestrator-never-builds` as a guard (`coordinator-scope`). That guard judges only a cloud coordinator's own writes. A local coordinator, and a triage or batch-runner session that spawns agents, are bound by the rule and are not judged. The schema has no partial marker, so the row reads as fully mechanized.

**Where.** `lint/rule_mechanisms.json` (the row for `roles-orchestrator-never-builds`). `hooks/guard.py` (`coordinator_scope_hit`).

**Decision.** `session-tiers` (tier guards: a coordinator stays in its tier, and a guard enforces it).

**Retire.** Either the guard also judges the other orchestrator tiers, or `lint/rule_audit.py` takes a partial mechanism kind and the row uses it. Check: the audit row names what the guard leaves open, or a test shows a local coordinator refused.
