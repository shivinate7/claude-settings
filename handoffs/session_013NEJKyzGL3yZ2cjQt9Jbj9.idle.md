# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKyzGL3yZ2cjQt9Jbj9

## Reply at 2026-11-10T17:23:23Z UTC

IDLE (B). Handoff, lane watchers-one-rule (step watcher-builtin-hook-survey, topic watchers-one-rule):
Goal: land owner items 180 a (events only, with three named exceptions: stall watcher, ci_wake, daily job) and 248 b (keep the six model-call hooks, state each one's cost, re-check on three triggers), each cost proven by a test.
PR #1349, branch lane/watchers-one-rule, head cfa2e589b (all pushed, draft, unmerged). It was released to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) on Nov 6. Review: code round 3 PASS at cd388f9ff (reviewer sonnet). The later commits change the plan only: ruling checks PASS at 302c291fc, 8d06a5c30 and cfa2e589b.
Files: .claude/rules/hooks.md (four exceptions; now also under janitor/**). Cost lines in docs/decisions stall-watch, ci-wait-reads-run-status, the-janitor-is-one-machine-wide-sweep, haiku-prompt-hooks, question-form. CostTests in 11 test files plus hooks/test_support/cost_probe.py. docs/plans/align-watchers.md section 6 holds Q1-Q7, all decided (items 180, 248, 249, 250, 304, 309). Notes went to docs/debts/notes.md.
Left: (1) bring the branch up to date with main, which has moved far since Nov 6, and re-run lint and tests, then batch; the plan's Q6 line is true only once PR #1369 merges. (2) Later steps: cost lines and tests for the other ~25 mechanisms (plan lane 2); the record check for rules 4-8 (plan lane 8, changes a check); a model-table row for local_time so the catalog shows its model call; sim-lease-tool rules 1 and 3 and skills/ios-apps/SKILL.md:70 still state the load bars (lane one-load-definition).
Worktree: /home/user/claude-settings/.claude/worktrees/watchers-one-rule, clean.

