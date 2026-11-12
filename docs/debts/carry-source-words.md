# Carry source words are too few

**What.** No check reads a source word now. `SOURCE_RE` is removed with the Recovered guard (decision cull-guard-wrong-refusals, the guard cull). This debt has no code left to fix.

**Where.** None. `lint/report_guard.py` has no `SOURCE_RE` and no `unsourced_recovered_item` after the guard cull.

**Decision.** precompact-handoff (checkpoints keep the handoff current). Its item 'Recovered line after compaction' is removed with the guard (decision cull-guard-wrong-refusals).

**Retire.** Closed by the guard cull. `lint/test_report_guard_cull.py` shows that a Recovered item with no source passes.
