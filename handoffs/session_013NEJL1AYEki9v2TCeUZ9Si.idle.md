# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL1AYEki9v2TCeUZ9Si

## Reply at 2026-11-10T17:25:35Z UTC

IDLE (B). Handoff, lane judge-no-readable-verdict (shivinate7/claude-settings):
Goal: the merge tool's prose judge must not let lines pass silently with "no readable verdict"; each unread line names itself as UNKNOWN.
Cause (measured): the judge runs `claude -p --tools ""`, and the model often replies with fake tool-call text instead of JSON. Replays of q_max #1125 and #1129 reproduced it.
State: both PRs are reviewed, have lane lint PASS, and are released to batch runner session_013NEJL2vsmyKzJm8jUDt6za. Neither is merged; at 6e8d6ccf9, main has no NO_TOOLS_NOTE.
- #1883 ("prose judge: tell line-verdict calls they have no tools, and name each unread line"), branch judge-no-readable-verdict, head c48b02909, Merge after: #1609 (pack prose judge lines into 3 parallel calls). Record: round 1 reviewer haiku FAIL, then the fix check PASS.
- #1928 (follow-up: names lines after an error partway through the loop or after a pack failure; strips control characters; debt record review-unparsed-refusal-msg), branch judge-nrv-followup, head 5285ebc4f, Merge after: #1883. Same record shape.
Files: hooks/decision_watch.py (NO_TOOLS_NOTE as --append-system-prompt, line-verdict shape only), merge/merge.py (prose_judge_plan/run), docs/decisions/claims-carry-backing.md, docs/debts/review-unparsed-refusal-msg.md, tests in merge/test_merge.py and hooks/test_decision_watch.py.
Measured: prose judge unread 12/20 → 0/20; prove_route_judge 8/20 → 0/20. The note on every caller moved two guards toward allow, so it stays scoped.
Left: only the merges, in order #1609, then #1883, then #1928. Scripts used for the replays: /tmp/claude-0/-home-user-claude-settings/5a013169-a946-5030-83e4-f1fde95819b2/scratchpad/ (measure*.py, audit/).

