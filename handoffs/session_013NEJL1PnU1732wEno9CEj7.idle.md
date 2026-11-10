# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL1PnU1732wEno9CEj7

## Reply at 2026-11-10T17:25:53Z UTC

IDLE (B). Handoff, lane capability-verbs-widen (topic report-guard; step record roadmap/data/steps/capability-verbs-widen.json on branch roadmap).
Goal: widen CAPABILITY_RE in lint/report_guard.py, one constant read by the chat-reply hand-off check (hand_off_problem) and the page-task check (why_yours_verdict, called from hooks/question_form.py). New: "could not", "couldn't", "rejected" (push/request/token/call/credential, active or passive; remote/server/API/GitHub/host rejected), and "401" when not after #. Must not refuse: "PR was rejected by review", "PR #401", "could not be (made/any) simpler".
State: done and reviewed (round 1 FAIL, round 2 PASS). Draft PR #1567, branch capability-verbs-stacked, head 7e7627c97, base main. Stacked on #1545 (page Why yours check, branch worktree-agent-ab257f32ecdac35a3, head 2b1f080d8). Handed to runner 8 (session_013NEJL2vsmyKzJm8jUDt6za), not merged.
Files: lint/report_guard.py, lint/test_report_guard_handoff.py, hooks/test_question_form.py, docs/debts/notes.md (two notes: capability-re-review-request, capability-re-bare-number).
Left: merge #1545, then #1567, after a rebase on current main, since base main is 174b005c1, far behind. The CI run has not happened yet. Branch capability-verbs-widen is stale: archive or delete it after the merge. Nothing is unpushed.

