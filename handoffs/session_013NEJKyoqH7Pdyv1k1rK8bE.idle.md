# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKyoqH7Pdyv1k1rK8bE

## Reply at 2026-11-10T17:22:38Z UTC

IDLE (B)
Goal: lane mutate-sweep-control. janitor/mutate_sweep.py gets a clean-layout control through mutate_shared.control_verdict, so a red, raising or timed-out control makes that suite's mutants UNKNOWN, never killed.
State: PR #1715 (sweep mutants: one clean-layout control per suite), draft, branch claude/mutate-sweep-ctl, head b456e502d, all pushed. It was handed to runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) and is not merged.
- It must merge after #1597 (clean-layout control per target), which is not on main yet.
- The review record is posted for b456e502d: round 1 PASS plus a fix check PASS, both reviewer haiku. guard or check: yes.
- `merge --lane-lint` passed on b456e502d against main e2703c611 (2026-11-08).
Step 2 (mutate-tree-collision) was dropped with the coordinator's agreement: the cfg_ check already refuses any tree_ clash. Its note row is removed.
Left:
- Main has moved a lot since 2026-11-08. Re-merge origin/main, resolve, re-run `merge --lane-lint 1715`, get a new fix check, and re-post the record. The decision ci-job-caps (CI job caps) text must stay identical to #1597's resolution.
- After #1715 merges, delete the old branch claude/mutate-sweep-control (235c00c94, the pre-rebase copy).
- Suggested, not built: step:builder-branch-held, a guard so a builder cannot `checkout -B` a branch another worktree holds.
Files: janitor/mutate_sweep.py, hooks/test_mutate_shared.py (CleanLayoutControlPerSuiteTests), docs/debts/notes.md, docs/decisions/ci-job-caps.md (from the merge only).

