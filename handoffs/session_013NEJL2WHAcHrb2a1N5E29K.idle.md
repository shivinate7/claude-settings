# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL2WHAcHrb2a1N5E29K

## Reply at 2026-11-10T17:26:59Z UTC

IDLE (B). Lane coordinator-pick-needs-record (shivinate7/claude-settings).
Goal: a rule about how work merges or batches cannot live only in a session handoff (step coordinator-pick-needs-record).
State: PR 1771 ("Refuse a handoff ruling line with no resolving home"), draft, open. Branch claude/coord-pick-needs-record, head 954f087a37c3f04bc23db3d2eea810abc507d35d, nothing unpushed. Released to runner 8 on 2026-11-08 at 04:24 CST. Review: round 1 FAIL (haiku), round 2 PASS (sonnet). Fix-check PASS record: https://github.com/shivinate7/claude-settings/pull/1771#issuecomment-6720312771. Batch 64 dropped it; both reds were fixed at 954f087a3.
What it does: a Stop check in hooks/ruling_home.py. When the turn wrote its handoff, each [ruling] premise and each line under "## Rulings with NO HOME YET" must end with `Home: <ruling record path>` or `Home: NO HOME YET (branch <real ref>)`.
Files: hooks/ruling_home.py, hooks/precompact_handoff.py, hooks/precompact_handoff_prompt.md, hooks/test_ruling_home.py, hooks/test_precompact_handoff.py, docs/catalog.md, docs/decisions/{premise-format,predicate-is-the-act,precompact-handoff}.md, docs/debts/notes.md (handoff-* notes).
Left:
(1) Merge PR 1771. Main is about 2800 commits ahead, so expect a re-merge of main, a fix check and a new review record at the new head.
(2) The prose form is not checked, by coordinator ruling 2026-11-07 22:46 CST. Its fix is step merge-builds-batches; note handoff-prose-rule-passes records it.
(3) Guard queued with the coordinator, not built: a push after a PASS requires a marker-form review record first.

