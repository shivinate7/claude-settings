# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL2GctUCgksFKSWZykD

## Reply at 2026-11-10T17:26:50Z UTC

IDLE (B)
Goal: stop lint codes (STALEnnn, STEnnn, MAPn) colliding across branches. Brief from the coordinator, 2026-11-07.
State: PR #1617 (lint-code check) is an open draft, branch lint-codes-unique, head 220d1e60f, every commit pushed. It is with runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) for the batch and has had no CI run. Review: round 1 FAIL, round 2 PASS (sonnet). The full merge/test_merge.py passed at c53b98a0d, and the commits after it change only notes.
Built: lint/check_lint_codes.py refuses a code the branch adds that the base tip already defines, and a new duplicate. A failed read is UNKNOWN (exit 2). It runs in the checks.yml "Lint code check" step (--head "$HEAD_SHA") and in merge/merge.py codes_check, at preview and at prove().
Left: runner 8 merges #1617. Then step lint-codes-r2-fixes (roadmap b8744af0b, todo) fixes 6 round-2 findings. They are the lint-codes-* lines in docs/debts/notes.md: cost pin 15, STALE row gap, max(tip, fork) duplicate count, more MAP forms, pre-claim codes_check, and a decision record lint-codes-unique.
Unhomed ruling: a home present at the base tip but absent at HEAD is UNKNOWN. Its home will be that decision record.
Files: lint/check_lint_codes.py, lint/test_check_lint_codes.py, merge/merge.py, .github/workflows/checks.yml, docs/debts/notes.md.
Check: python3 lint/check_lint_codes.py --base origin/main --root .

