# o4 part 2, words probe (lane session_013NEJL2AASrXXJB2wtjfDeg)

- PR #790 (draft), branch o4-words-probe, head c9352aab. Reviewed: round 1 FAIL (sonnet), round 2 PASS (sonnet).
- Local gates PASS at c9352aab: unittest lint.test_compliance_probes, ci-job checks --lint --base origin/main, ste-changed, check_silent_undo --strict.
- Words run on claude-settings at c9352aab (GLOSSARY.md and lint/check_glossary.py same as main 60216ac9): 137 items. deny 105, gate 18, subagent 3, owner word 2, hole 2, block 2, worker 1, issue 1, approval 1, try 1 and gap 1 (both pending the o13 restore lane), claim 0. One unread file (a png).
- Notes from round 2, not built: one hit prints twice when the glossary gives the word two terms (gate); a deleted tracked file or a submodule counts as unread.
- Status: green and reviewed; waits on the orchestrator's batch.
