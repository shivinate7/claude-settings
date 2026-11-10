# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL1xdQmJC85BLQucDP9

## Reply at 2026-11-10T17:26:35Z UTC

IDLE (B). Lane reviewer-model-hook-latest, repo shivinate7/claude-settings.
Goal: stop the report Stop hook's model-name check (rule reports-done-names-models) from flagging a correct model name from an earlier review round.
Cause: the spawn window started at the last is_last_human record. isMeta machine records reset it: the system-reminder record before each agent hand-back, and "Stop hook feedback:".
Fix: `last_owner_index` in lint/_transcript.py and `spawn_window` in lint/report_guard.py. The window starts at the last incoming record that is not isMeta and has no peer origin, or at a peer brief. With neither, it is the whole transcript. The rewrite path is bounded by `upto`.
State: PR #1401, an open draft, branch reviewer-model-hook-latest, head fa8198a425946f6f9bec66fe350a946261742763, base e2703c611 (two days old). Nothing is unpushed.
- Review record posted: round 1 haiku FAIL, round 2 sonnet PASS, guard yes. `merge --lane-lint 1401` PASSED.
- Handed to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) on 2026-11-08 at 04:51 CST. It has not merged.
- Stacked #1438 (lane model-guard-reads-next) waits on it.
Left:
- Runner 8 merges #1401. It may need main merged in first; if the head moves, the review record needs a fix check.
- Four notes are filed in docs/debts/notes.md (spawn-window-*).
- Fired-wake shape measured: not isMeta, origin.kind task-notification. Recorded in the PR body.
Files: lint/_transcript.py, lint/report_guard.py, lint/test_report_guard.py, docs/debts/notes.md.

