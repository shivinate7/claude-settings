# Handoff: lane ci-split-checks-jobs, 2026-11-19

- Slug: `ci-split-checks-jobs` (triage step `ci-split-checks-jobs`; adopted step `ci-split-checks-family`).
- Repo: shivinate7/claude-settings. Session: session_013NEJL2UPotZrZRQ9WLTshH.
- Role: lane (one line of work, own agents). Parent: coordinator session_013NEJL1gw6EdrSyvHkTUEx6. Batch runner: runner 10, session_013NEJL2f1YCYsvLdpFqtWP3. Triage: session_013NEJKzCzoWhfP8FMCPtQU6.

## State

- The work is landed. PR #3376, branch `ci-split-checks-v2`, head `c0476cab1241f9f58f2a22bccbf91d2e019bc63d`, merged 2026-11-14 09:15 UTC (merge commit `4db2a9cf3c109e58d9929763b5ae739ae743cca0`). Read from the GitHub REST API at 00:30 CST Nov 19.
- PR #2980, branch `ci-split-checks-family`, head `b875e556ed39896f82241a1f7bfc789c02744156`: closed, not merged. Replaced by #3376 (same tree).
- No open PR of this lane. This handoff branch opens none.

## What was done

- Split the Linux `checks` job into `checks` (lint family), `checks-hooks`, `checks-rest`. Both new jobs are in the `needs:` of all-jobs-passed and ci-done. Step list before and after: 173 steps on main, 177 across the three, only checkout and setup-python added per new job.
- Guard cases in `lint/test_windows_split.py`: a lint step (by `bin/ci-job`'s own `is_lint`) in any Linux split job but `checks` fails; a step name repeated across the four Linux jobs fails.
- Review: #3376 round 1 haiku FAIL, round 2 sonnet PASS, Guard or check: yes, net value not owed. #2980 had its own rounds and fix checks; two fix checks failed on the way (two lint steps landed outside `checks` after a main merge), both fixed.

## Measured (read from the run, not projected)

- Before: push run 43559463664, `checks` alone, 148 steps, 40.7 min of steps (41.2 min with setup).
- After: #3376's ready PR run 43573255496 (head c0476cab1, success): `checks` 15.5 min, `checks-hooks` 11.8, `checks-rest` 10.0, `checks-merge-install` 20.6 (the slowest Linux split job). The whole run's other jobs were not read.

## Unfinished

- Nothing owed by this lane on #3376.
- Open for others: step `lane-lint-runs-all-suite-jobs` (filed by triage, ready): lane lint runs picked suites in every `CHECKS_SUITE_JOBS` job. For a `hooks/` diff, `checks` runs 102 of 107 steps instead of 139 of 173, and 37 picked hook suites read "not run, job checks-hooks runs them" (coordinator accepted for #3376, 00:39 CST Nov 14). Cost of the fix: unmeasured.
- Next step for the floor: `checks-merge-install` (20.6 min) is now the slowest Linux job; a further split of it or of `checks` is a new step for the coordinator.

## Refused acts and tool refusals

- Carry of #2980's review record to #3376 by tree: refused by `merge --review-record --fix-check` (decision `pr-review-record`, needs an earlier log on the same PR). Sent to the coordinator; fresh rounds ran.
- Push of #2980's last commit with no `Red-run` trailer: lane lint refused; the pushed commit could not be reworded, so the branch was rebuilt as #3376.
- The record parse miss: a notes paragraph after the printed record lines made the newest record unreadable (`merge --reviewed` read "bad"). Reposted the printed form only. A guard that refuses extra text after the printed lines is not built or queued; for the coordinator to file.

## Owner rulings I hold

- None of my own. Relayed: coordinator 00:39 CST Nov 14 (accept the lane-lint coverage gap for #3376 only); no fixed time targets (owner 11:36 CST Nov 13, via the coordinator). The 11:35 CST Nov 13 task message is filed in my feedback inbox as a note, not a grant.

## Agents (each one role, none running)

- test-author a40c0967f821743e1, stopped before it wrote anything; worktree clean.
- reviewers (fix checks): a9a7d85035aec4c76 (FAIL), a9ef832430ec3478c (FAIL, stable-workflow step), a90c9ab5d73784f0c (PASS), a294f8dcb1a7893a0 (PASS), a361629141eecfcf2 (stopped), af1000a91d80d9aed (round 1 haiku FAIL), a36c1fb2b5845aa38 (round 2 sonnet PASS). No branch of their own; they read branches `ci-split-checks-family` and `ci-split-checks-v2`.

## Branches and worktrees

- `ci-split-checks-family` (origin, #2980), `ci-split-checks-v2` (origin, #3376, merged). Local worktree `.claude/worktrees/ci-split-checks-adopt`, branch `ci-split-checks-v2`, clean, no unpushed commit. The same tree as #2980 is on main.
- This file: branch `archive/handoff-ci-split-checks-jobs`.
