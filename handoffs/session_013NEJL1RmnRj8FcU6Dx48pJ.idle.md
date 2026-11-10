# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL1RmnRj8FcU6Dx48pJ

## Reply at 2026-11-10T17:25:57Z UTC

IDLE (B)
Goal: step red-checkout-restore-absolute (798): guard against a relative `git restore`/`git checkout` landing in the agent's own tree while its own red-run folder is named in another segment of the same command.
State: built, reviewed (round 1 FAIL haiku, round 2 FAIL sonnet, round 3 PASS sonnet, net value positive, fix check PASS) and handed to batch runner 8. Nothing running, nothing unpushed.
PR: draft #2259, head fde2398a6b47d003594e313eee3947fec3728f74, branch red-checkout-restore-absolute. Merge after #1984 and #2197 (sits on #2197's head e7f7ab9c3). Review record posted at the live head.
Left: the merge by batch runner 8. Lane lint vs main shows 3 FAILs inherited from #1984/#2197 lines (test_guard.py:21976 comment, record line 27 and notes.md:939 sentence length); my glossary FAIL is fixed. Full mutate_guard not run.
Limit kept in the record: the clause reads one command; a red path named in an earlier call is not caught (incident text unknown; follow-up only on a second incident).
Files: hooks/guard.py (relative_restore_for_red), hooks/test_guard.py, hooks/mutate_guard.py, docs/decisions/an-agent-outside-its-home-tree-must-stop.md, docs/debts/notes.md.

