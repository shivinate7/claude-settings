## Waiting on the owner in this session

none

## Goal

Lane lint follows the pinned trees as CI does: keep `pin_tree`, drop `--pinned`, port #1938's per-step pins onto it. Source: owner page answer, item 727 option a, 2026-11-15 11:57:48 CST (ruling own-727-a-pin-tree-drop-pinned); lane brief 12:29 CST Nov 15.

## Working premises

- P1 [ruling] No `--pinned`; `pin_tree` resolves a moving ref to its commit, then archives it. Source: own-727-a-pin-tree-drop-pinned on origin/roadmap. Checked 2026-11-15.
- P2 [ruling] Item 900 option a: keep the `merge --ready` allow rule and re-point the CloudAllow test. Source: waiting-page database, answers/merge-ready-allow-rule-vs-test, saved 2026-11-15 18:12 CST. Checked 2026-11-19.
- P3 [read] After my last work (63b3e5bcb5), others pushed to the branch on Nov 18: 5cc35d5f6c (merge main), da2b644ece (notes moved to one file each), 6ee59752df and 17687a3714 (`--lint` still runs the pinned ste-lint when the stable fetch fails, with the reason as a note). That last change differs from my round 1 fix A, which made a failed fetch unknown under every mode. Source: git log 63b3e5bcb5..origin/lane-lint-pin-tree-steps. Checked 2026-11-19.

## Where things stand

- Lane slug `lane-lint-pin-tree-steps`; branch head on origin 17687a37149f65fde1001ee7dda64d805154bcf6.
- PR #3551, draft, open, head 17687a3714, base 7c8c180b52, 22 commits, 2 comments. The last verdict I have is for 63b3e5bcb5 (three suites 2345 passed, 6 skipped, 0 failed). Heads after it are unverified by me.
- Done: red cases, build, review round 1 FAIL then fixed, round 2 PASS (sonnet), notes, PR body with the `Rules checked: lanes-run-no-full-ci-job — no change` line.

## Work in flight

No agent is running. Agents (all finished): test-author a268ac0f2b7bdb03f (worktree-agent-a268ac0f2b7bdb03f), builder a4a298162780bf645 (worktree-agent-a4a298162780bf645), round 1 reviewer a373fa78ddbae9eeb, round 2 reviewer acd8c7cd115d91351. All pushed to lane-lint-pin-tree-steps.

## Next steps

1. Unfinished: the re-land of #3542 (the `merge --ready` allow rule, the test fix, `merge/cloud_allow.json` count, `caseM1` count: 4 merge allow rules). Triage said it would file step `reland-merge-ready-allow`; I saw no such step on origin/roadmap at 2026-11-19 00:24 CST, so it was never started.
2. Re-run `merge --lane-lint` on the current #3551 head (the PR body now has the aligned line) and read CI once on the head runner 10 merges.
3. Check the Nov 18 change to the stable-fetch failure under `--lint` (P3) against ruling 727 and the round 2 review.
4. Hand to runner 10 to mark ready and merge; this lane never marks ready.

## Files and commands

- bin/ci-job, bin/ste-changed, hooks/action_pin.py, merge/merge.py, merge/combine_train.py.
- Tests: lint/test_ci_job.py (PinnedHarness), merge/test_merge.py, merge/test_lane_lint.py. Check: `python3 bin/verdict /root/.local/bin/pytest -q <the three files>`.
- Refused acts: worktree add on the old sha (the guard refused it for the test-author); `SendMessage` to a session id (use the send_message tool). Owner rulings held: own-727-a-pin-tree-drop-pinned, item 900 a.
- Triage page writer session: session_013NEJKzCzoWhfP8FMCPtQU6.
