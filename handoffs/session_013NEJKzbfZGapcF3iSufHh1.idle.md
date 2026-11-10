# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKzbfZGapcF3iSufHh1

## Reply at 2026-11-10T17:24:01Z UTC

IDLE (B) — lane step-grant-judge-marker hand-off.
Goal: owner page item 295 a (2026-11-06 13:51 CST). A roadmap step grant may carry "marker": "Judge:". It then covers only an Opus spawn whose brief's first non-blank line carries Judge:, read like Audit:. In a call with several Opus spawns, each spawn with no standing grant must carry it. A marker only narrows.
State: PR #1352, branch step-grant-judge-marker, head 36cb6fdd399497aa4b02980ae4ac1db4f571ad5d, open. Main e2703c611 merged in. Lane lint PASS on this head. Review record posted for this head: round 1 haiku FAIL, round 2 sonnet PASS, fix check haiku PASS, guard yes. Handed to runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) 2026-11-08 04:26 CST. Not merged.
Files: hooks/shared_names.py (JUDGE_MARKER, BRIEF_MARKERS judge row, GRANT_MARKERS), hooks/guard.py (opus_spawn_hit kinds intersection; 9d spawn_markers), hooks/guard_core.py (refuse spawn_markers → take), hooks/override.py (_grant_cover, _take_step), hooks/mutate_guard.py (7 rows), hooks/test_guard.py (24 judge-marker cases), docs/decisions/agent-model-cap.md, docs/debts/notes.md.
Roadmap: triage wrote the marker on step prose-governance-workflow (roadmap 8721bcea).
Left: main has moved on by many commits since e2703c611. Before batching: merge main again, re-run `merge --lane-lint 1352`, post a fresh review record. Open notes: opus-ceiling-first-spawn-role (role-only grants judge only the first spawn, as on main). The fix check on the main merge 40f2c12de is in no record; the tool takes a fix check only after an earlier record.
Nothing unpushed.

