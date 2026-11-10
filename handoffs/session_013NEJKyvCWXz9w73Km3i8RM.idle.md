# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKyvCWXz9w73Km3i8RM

## Reply at 2026-11-10T17:23:05Z UTC

IDLE (B). Handoff, lane cloud-snapshot-age-check:
Goal: a cloud session warns once when its environment snapshot runs stale startup hooks, and names the fix (edit the environment, save the Setup script).
State: PR #1363 (stale cloud snapshot warning), open draft, branch cloud-snapshot-age-check, head 210c1ef. Review round 3 PASS (sonnet). It was handed to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) and waits for its merge. Nothing is unpushed.
Rulings: coordinator 2026-11-06 14:42 CST, trigger (b): warn on a stale startup entry in the snapshot's settings.json, never on hooks/ lag; no marker. Lane, after round 1: local state only; a no-input run warns when CLAUDE_PROJECT_DIR is set. Both are recorded in decision cloud-start-hooks-run-fresh (Limits, first bullet).
Files: install.sh (REFRESH_CURL, REFRESH_HEAD, the warning before the settings.json write); hooks/test_install_src.sh snapstale1-11; docs/decisions/cloud-start-hooks-run-fresh.md; docs/debts/notes.md (two notes: snapstale-project-dir-unmeasured, snapstale-refresh-literal); docs/debts/lane-branch-in-two-worktrees.md (a debt).
Left: the merge by a batch runner, and the step note on the roadmap branch rewritten to trigger (b). The text is in the PR body, and the edit is the coordinator's. Open: CLAUDE_PROJECT_DIR in the cloud hook env is unmeasured.

