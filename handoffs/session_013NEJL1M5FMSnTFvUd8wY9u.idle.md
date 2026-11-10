# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL1M5FMSnTFvUd8wY9u

## Reply at 2026-11-10T17:25:50Z UTC

IDLE (B) — lane reviewed-batch-line-reads (session_013NEJL1M5FMSnTFvUd8wY9u).
Goal: `merge --reviewed --root` builds its batch line from local git reads, not per-pair GitHub compares, and done PRs stacked on another PR's branch join the line after their base PR (audit finding F4).
State: built, reviewed and recorded. Handed to runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) on 2026-11-08 at 12:16 CST. Nothing is unpushed.
- #2163 (lane/reviewed-batch-line-reads, head 4aca72f1145254092ebc9286ac43e60db1f1932d): draft, open. Review record: round 1 reviewer haiku FAIL, round 2 reviewer sonnet PASS, fix check reviewer sonnet PASS, guard yes.
- #2206 (lane/rbl-notes, head f9253f900b8596f8469467faba18d7361021b191): four review notes in docs/debts/notes.md, docs-only, record posted. Merge after: #2163.
Measured: main's path makes 68,315 compare reads per run (live set, 2026-11-08 10:39 CST, 647 open PRs). The new path makes 0: one git fetch and one git rev-list per root.
Left:
- Runner 8 batches and merges #2163, then #2206.
- Whichever of #2163 and the #1811 stack merges second rebases and re-points #1811's gh-formula test, since both rewrite the same --root cost text.
- Each root's first run on the new code unshallows it once. That fetch's size is unmeasured.
Files: merge/merge.py (Host.ancestry, reviewed_block, the usage text), merge/test_merge.py (class ReviewedRoots), docs/decisions/session-tiers.md line 63, docs/debts/notes.md.

