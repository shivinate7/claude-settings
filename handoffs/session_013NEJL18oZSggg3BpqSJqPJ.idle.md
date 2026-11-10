# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL18oZSggg3BpqSJqPJ

## Reply at 2026-11-10T17:25:29Z UTC

IDLE (B). Handoff, lane merge-red-main-latest-run (parent coordinator session_013NEJL2hB1pLZPDpzas7VgB):
Goal: roadmap step merge-red-main-latest-run. Route D: the merge tool's red-main refusal names `gh run rerun <id>` for a cancelled newest run on the base's head. The verdict is unchanged.
State: PR #2492, branch mrmlr-build2, head 21eb52bee2a5ce974f627b818fbfc4641f8857ad, still an open draft, mergeable clean at 11:25 CST. Base main 0e6509a96. Parent released it to runner 8 for batch 72 at 01:34 CST; it has not merged.
Checks done: lane lint PASS on this head; round 1 FAIL (fixed), round 2 fix check PASS, round 3 net value zero. Review record is comment 6761697673 on #2492.
Left: the batch runner merges it. A merge-tool note for triage: a malformed run row with no `event` key now reads unknown (fail-closed); two other notes are in the PR body.
Files: merge/merge.py, merge/test_merge.py, docs/decisions/no-merge-onto-red-main.md. Nothing unpushed. Nothing is running.

