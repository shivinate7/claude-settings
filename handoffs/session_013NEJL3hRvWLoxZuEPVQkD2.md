# lane: agent-served-model-check (session_013NEJL3hRvWLoxZuEPVQkD2), received 11:05 CST 2026-11-10, kind B

Handoff (B), resent; lane agent-served-model-check, session_013NEJL3hRvWLoxZuEPVQkD2. Nothing unpushed.
1. Work: a reviewer on a fix check brief must name sonnet (guard rule agent-role-model), and every agent file pins a model (agents/builder.md now `model: sonnet`, plus a lint rule). Measured: per-spawn model beats the file pin, which beats the sonnet env default.
2. Repo shivinate7/claude-settings, branch agent-served-model-check-build-2, PR #2486 (draft), head 6d3bfd0b2. Review record posted (comment 6761716117): haiku FAIL, sonnet PARTIAL, sonnet PASS, net value positive. `merge --lane-lint 2486` PASS on that head.
3. State: not released to the batch runner. #2486 conflicts with #2442 (same decision file agent-model-cap.md); the coordinator said hold until #2442 merges.
4. Left: after #2442 merges, merge main (a test-author if a test file conflicts), a fix check chained from the posted record, `merge --lane-lint 2486`, then hand head and record to the coordinator.
5. Debt candidates already with the coordinator: the review-record tool cannot chain a fix check when the head moves after the last round; no served-model-equals-requested check at agent end.
