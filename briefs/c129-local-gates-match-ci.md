# Brief: c129, the local gates run matches CI

Repo: shivinate7/claude-settings, from main 43d9af20 (batch #698). One lane: builder (sonnet), then reviewer (sonnet).

## Task
Two gaps between `bin/ci-job gates --lint` and the gates job in CI.
1. gates.yml runs the STE lint as a `uses:` action step, so `ci-job --lint` skips it. Make the local run cover it: either a `run:` step in gates that calls `bin/ste-changed`, or `ci-job` that knows the action and runs `bin/ste-changed` in its place. Pick the one with one home for the STE check; say which and why.
2. `lint/test_check_silent_undo.py::test_a_gitlink_with_an_absent_commit_is_not_unknown` errors in a cloud container with git 2.43 (path: check_silent_undo's absent-commit read). Find the cause. Fix it if the check is wrong on that git; if only the test is wrong, re-point it; if neither can change, record a debt with the git version and the read.

## Rulings
- outcomes-tests-are-claims (re-point or fix, never skip).
- building-one-home-per-capability.

## Failure classes
- A local run that says green while CI's STE step would go red.
- A silent-undo check that reports "clear" for an absent commit on some git version (a missed undo).

## Check that proves it done
(1) a test of ci-job (lint/test_ci_job.py) red on main: the gates lint run on a branch with an over-long sentence in a changed .md does not fail; green on the branch. (2) the silent-undo test red in this container on main, green on the branch; state `git --version`. `python3 bin/ci-job gates --lint --base origin/main` and `bin/ste-changed origin/main` pass.

## Report
At most 12 lines: PR (draft), head, red runs, green runs, review verdict. Send the green, reviewed head to the build advisor thread "Advise the claude-settings build (9)". Do not rebase onto main and do not merge.
