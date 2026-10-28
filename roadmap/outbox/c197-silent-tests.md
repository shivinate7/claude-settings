# c197 silent test files: stopped before any change (Oct 28, 13:5x CDT)

No branch pushed, no PR. Worktree branch c197-silent-tests is clean at origin/main f1f7fa92.

## Recount
Measured: every test file in the repo (all test_*.py, *.test.mjs, test_*.sh, *.test.ps1) is named by a step in .github/workflows/checks.yml, or is picked up by a glob in .github/scripts/mod-tests.sh (mods/*.test.mjs) or `node --test` in skills/plain-english-map/tests. The workflow has no continue-on-error and no `|| true`. Zero files are un-run. hooks/case_runner_test.py is a shared helper, not a suite.
The six files the step names all run in checks and all pass today (exit 0, 116 / 51 / OK cases):
hooks/test_wrappers.py, lint/test_rule_audit.py, lint/test_settings_matcher.py, lint/test_hook_platform_exit.py, janitor/test_session_end_sweep.py, hooks/test_reply_judge.py.
Planted failure in each (red first): every file exits 1 today. So "silent" here is not "not run" and not "result not read".
Seventh file: none found. The step's own six is the number; shiv's 7 is unexplained.

## What "silent" actually is
docs/debts/notes.md silent-suite-* lines: the mutation report found that each suite killed none of 10 mutants of a file it was scored against (report_guard.py, feedback_guard.py, stall_watch.py). These suites test other things (wrapper shape, platform exit, hook registration, rule audit). The mutation report's suite-to-file attribution is unmeasured by me; I did not run it.

## Deferred: why
Wiring in CI is already done, so there is nothing to wire. Two real choices need a ruling (stale-record protocol, outcomes-stale-decision-protocol):
A. (recommended) Record only: close the six silent-suite-* debts as misattributed (suites do not claim those files; dedicated suites test_report_guard, test_feedback_inbox, test_stall_watch* already kill the mutants), and fix or note the mutation report's attribution. Net-value check not needed: no deletion.
B. Add mutant-killing tests of report_guard / feedback_guard / stall_watch into these six files. Duplicates existing suites (building-one-home-per-capability).
C. Delete files. Loses pinned wrapper/registration/platform-exit behaviour for no gain.
