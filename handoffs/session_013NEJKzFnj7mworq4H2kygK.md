# lane-lint-in-isolated-worktree (session_013NEJKzFnj7mworq4H2kygK), received 09:47 CST 2026-11-10, kind B

Handoff (B), lane lane-lint-in-isolated-worktree, session_013NEJKzFnj7mworq4H2kygK:
1. Work: step lane-lint-in-isolated-worktree. One sentence in skills/project-ops/templates/brief.md: run `merge --lane-lint` from the main checkout, never from a session or agent isolated in a worktree; the worktree check "can refuse it there". Plus a pin test.
2. Repo shivinate7/claude-settings, branch lane-lint-in-isolated-worktree (pushed, nothing unpushed), PR #2531 (draft), head 3720c6b890fa53c49aa14adce35e8cc52e6a2fcf.
3. State: review record posted (comment 6767626215: round 1 FAIL, round 2 PASS, fix check PASS), `merge --lane-lint 2531` PASS on that head. Not released to a batch runner; PR still draft.
4. Left: batch runner takes #2531 and marks it ready/joins a batch. Step note could add my repro: lane lint refused in a worktree session as a background command, accepted in the foreground. Mutant check not run on the final head.
