# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKyoXvBfn7q6bpofjYg

## Reply at 2026-11-10T17:22:36Z UTC

IDLE (B). Lane habit-is-not-a-guard.
Goal: owner ruling 2026-11-08 11:27 CST, "a habit is no guard". A report's guard line must name a PR, a commit, step:<slug> or a debt.
State: PR #2183, shivinate7/claude-settings, branch habit-is-not-a-guard, head 938d179eeff4b92fa5bdfd8842f3304d0f0bf6dc. It is a draft, open, and not merged. Base is 422cbbdfe, which is now far behind main, so a rebase or main merge may be needed.
Review: round 1 FAIL (haiku), round 2 FAIL (sonnet), round 3 PASS at this head (sonnet), net value positive. The review record is posted as a PR comment (issuecomment-6725624555). It went to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) on 2026-11-08 at 12:56 CST.
Files: CLAUDE.md (rule building-mistake-names-its-guard), docs/decisions/mistake-means-missing-guard.md (the ruling, the incident, the check's spec), lint/report_guard.py (mistake_problem, the guard-line check), lint/test_report_guard.py (MistakeNamesGuardTests, 35 new cases), lint/rule_mechanisms.json (test anchor), docs/debts/notes.md (7 notes, guard-line-*).
Left: batch it and merge it, after a main merge and CI green. A main merge needs the silent-undo check run (step merge-main-silent-undo-precheck). A new review record is needed if the head moves.
Leftover: the test-author's red checkout .claude/worktrees/agent-a68bf09a3b73503f4-red, for a sweep.
Possible false alarm: the refusal guard (refusals-reach-the-owner) re-fires on every reply after an auto-mode refusal has already been raised.

