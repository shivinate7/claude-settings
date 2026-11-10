# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKzJF4PJoASnkH4btJj

## Reply at 2026-11-10T17:23:21Z UTC

IDLE (B)
Goal: roadmap step ruling-skip-check (owner item 284 b, 2026-11-06 13:08 CST). When a report's Done item says a pick was taken under a ruling, it must cite the ruling (item N key, or a decision id, plus a time). A blind Sonnet refuter then confirms that the ruling names that act. Anything unknown refuses.
State: draft PR #1343, branch lane/ruling-skip-check, head a83c0686, all pushed. 3 review rounds; round 3 PASS, net value positive. Handed to batch runner 8 on 2026-11-06; it has not merged. Its base (5e595822) is far behind main, so it needs a rebase, and CI has not run.
Files: lint/report_guard.py (RULING_REFUTER_MODEL, ruling_skip_problem, STOP_BUDGET of 30 s), hooks/question_form.py (read_json_folder), lint/test_report_guard_ruling_skip.py (22 cases), hooks/test_call_judge.py, hooks/mutate_guard.py, .github/workflows/checks.yml, .github/scripts/ci-scope.sh, docs/decisions/questions-go-to-owner.md (ruling-skip bullet).
Debts filed: ruling-skip-pick-word-alarms, ruling-skip-stale-roadmap, ruling-skip-reason-no-record. Two lines in docs/debts/notes.md.
Left: rebase onto main, re-run the suites, CI in its own batch (it changes a check), then merge.

