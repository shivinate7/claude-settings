# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL44p2pd4nwYgCQXqTg

## Reply at 2026-11-10T17:29:00Z UTC

IDLE (B). Lane session_013NEJL44p2pd4nwYgCQXqTg, step artifact-guard-matcher-names.
Goal: guards fire on Mac mcp__claude-artifacts__* calls (db_write, db_str_replace, db_get, db_list, db_query, publish_files) through one normaliser, normalize_data_call in hooks/shared_names.py; matchers extended; permissions.allow unchanged.
State: repo shivinate7/claude-settings, draft PR 2549, branch ta4-artifact-guard-matcher-names, head e034db8de4857c03d7220085700766e82863659d, still open and unmerged (read 11:29 CST). Review record plus fix-check record posted; rounds 1 and 2 FAIL then fixed, round 3 PASS, net value positive. Lane lint: UNKNOWN at the 1200 s cap, no failed step. Coordinator released it to runner 8 at 10:09 CST. PR 2548 is closed (replaced).
Left: runner 8 merges 2549 on green CI. Branch artifact-guard-matcher-names on origin holds the same commit; delete it after the merge.
Debts filed in the PR: mac-artifact-id-key-unknown, mac-str-replace-text-keys (the Mac artifact id key needs one redacted db_write input from the owner's Mac).
Files: hooks/shared_names.py, hooks/guard.py, hooks/call_judge.py, hooks/local_time.py, hooks/feedback_guard.py, hooks/question_form.py, lint/_transcript.py, lint/report_guard.py, settings.json, docs/debts/ (2 files), tests in lint/test_settings_matcher.py, hooks/test_*.py, hooks/mutate_guard.py.

