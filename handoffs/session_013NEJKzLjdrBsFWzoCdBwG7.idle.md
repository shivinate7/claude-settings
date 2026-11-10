# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKzLjdrBsFWzoCdBwG7

## Reply at 2026-11-10T17:23:42Z UTC

IDLE (B)
Goal: lane substitution-in-token-callers, steps substitution-in-token-callers and push-calls-substitution-mutant. Guard callers now read a command inside $( ) or backticks.
State: done. Draft PR #2151 (branch substitution-callers-r3, head d6a68f1a159f1a491406357e91619b9e262a069c, base main at 422cbbdfe) was handed to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) for batch 65.
- Review record on #2151: round 1 FAIL (reviewer haiku), rounds 2 and 3 PASS (reviewer sonnet), net value positive. merge --lane-lint d6a68f1a1 PASS.
- #1762 (branch substitution-in-token-callers) is replaced by #2151 and can be closed. It lacked a Red-run trailer on a comment-only commit, and adding one would have needed a force push.
- archive/substitution-callers-r2 holds a superseded try. Nothing is unpushed.
Left:
- Runner 8 merges #2151. If main has moved and #2151 conflicts, merge main into it and run lane lint plus a fix check.
- Filed as notes in docs/debts/notes.md: substitution-nested-rm-false-alarm, substitution-nested-cd-root, linked-nm-substitution-cd, substitution-cd-segments-slow (38 s for 1000 segments here; 62 s on another shape, past the 60 s hook limit), plus the guard-substitution-in-token heredoc item.
- Unfiled gap: no guard catches a lane that pushes after a review without first posting its review record.
- hooks/test_question_form.py:1210 still says "refused on main". That comment came from main, so it is left for #1879.
Files: hooks/guard.py, guard_merge.py, guard_rm_var.py, question_form.py, mutate_guard.py, test_guard.py, test_question_form.py, docs/debts/notes.md.

