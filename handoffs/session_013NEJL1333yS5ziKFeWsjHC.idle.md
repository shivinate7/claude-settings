# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL1333yS5ziKFeWsjHC

## Reply at 2026-11-10T17:25:35Z UTC

IDLE (B). Lane agent-report-shas-resolve.
Goal: refuse an agent hand-back, or a send_message, that names a commit, PR or PR comment that does not exist (coordinator brief, 2026-11-08 01:20 and 02:30 CST).
State: all built, reviewed and pushed. Nothing unpushed, nothing running. Three open PRs, released to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za), to merge in this order:
- #1842, made-up shas in agent reports. Branch agent-report-shas-resolve, head 3e5acf1ef, record issuecomment-6727520027.
- #2235, refs in messages between sessions (Merge after #1842). Branch send-message-refs-resolve-r2, head 421521c49, record issuecomment-6726353070.
- #2265, a PR word apart from its number (Merge after #2235). Branch msg-ref-pr-forms, head 9a97ca39b, record issuecomment-6727182711.
Each record has rounds 1-3, net value positive, and lane lint PASS.
Left: merge them. Main has moved far, so expect conflicts. On a conflict: merge main into the branch, run GUARD_FAMILY=report-sha-missing and message-ref-missing through verdict, run the lane lint, get a review record for the new head, then re-hand.
Files: hooks/guard.py, hooks/test_guard.py, hooks/shared_names.py, hooks/mutate_guard.py, settings.json, docs/decisions/agent-report-shas-resolve.md, docs/decisions/send-message-refs-resolve.md, docs/debts/notes.md.
Notes still to file: triage holds the round 3 notes. Closed #1864 left archive/send-message-refs-resolve and an unused branch, message-ref-pr-forms.

