# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL1q9xCaEWZfB6KebLx

## Reply at 2026-11-10T17:26:49Z UTC

IDLE (B). Lane mutate-guard-split handoff:
- Goal: split CI job checks-mutate-guard into shard jobs, each under 25 min, and retire debt mutate-guard-split.
- PR #1689 (draft), branch mutate-guard-split, head b2fb48f17, fully pushed. Base claude/mutant-crash-audit is #1597 (clean-layout controls, open), which has since moved to 758aafe1d. GitHub showed #1689 as conflicting on 2026-11-08.
- Built: checks-mutate-guard, -2 and -3, each with MUTATE_SHARD=i/3 and a 25 min cap. A guard-suite clean-layout control runs as 4 GUARD_SHARD sub-runs (CONTROL_SPLIT). The guard, override and simlease targets run every hooks/test_guard*.py.
- Measured: run 42431817106 on 9a54dcffa took 17.0, 8.3 and 12.4 min per shard job, and every mutant was killed.
- Reviews: round 1 FAIL (reviewer haiku), rounds 2 and 3 PASS (reviewer sonnet), fix check PASS (reviewer haiku). Net value zero. The review record for b2fb48f17 is on #1689.
- Records: debt mutate-guard-split retired; debt mutate-unknown-flag-runs-all added; notes lines mutate-shard-blank-runs-all, mutate-control-split-green-unpinned and mutate-control-split-wait-unpinned; decision ci-job-caps holds the figures.
- Left:
  - Merge #1597 first, or rebase #1689 onto its new head and settle the conflict. Either one needs a fresh review record for the new head.
  - At merge, rebuild docs/records.md, or Hook catalog R10 stays red.
  - checks-windows-guard-2 was red on main too, so it is not this lane's.
- Files: hooks/mutate_guard.py, hooks/test_mutate_shared.py, lint/test_windows_split.py, lint/test_all_jobs_passed.py, .github/workflows/checks.yml, docs/decisions/ci-job-caps.md, docs/debts/notes.md, docs/debts/mutate-unknown-flag-runs-all.md.

