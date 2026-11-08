# Lane lint never runs the guard suite

**What.** `merge --lane-lint` never runs `hooks/test_guard.py`. The `checks-guard` job gets its NODE_PATH install only from the composite action `actions/playwright-setup` (npm ci, a browser download, optional apt). Lane lint skips a `uses:` step, so the suite reads as one `not run` line. A lane that breaks the guard suite passes lane lint and goes red in batch CI. Claude is likely to hit it, since any lane that edits `hooks/guard.py` picks that suite.

**Where.** `other_job_runs` in `merge/merge.py`, `MISSING_INSTALL_LINE` in `lint/workflow_steps.py`, and `bin/ci-job` (the skipped `uses:` step).

**Decision.** `lanes-run-no-full-ci-job`, the lane lint runs the picked suites and not the full CI job.

**Retire.** Lane lint runs the install of `actions/playwright-setup` by that action's own home, then runs hooks/test_guard.py. The suite then reads `PASS` or `FAIL` in lane lint, never `not run`. Proof: `merge/test_lane_lint_guard_suite.py`, the file, added by the fix, that lane lint runs checks-guard's guard suite after the Playwright install.

Fix: queued as step lane-lint-guard-suite-install (proposed to triage). The fix lane must re-point the test `test_a_picked_suite_whose_env_node_path_is_not_installed_here_is_one_not_run_line_naming_the_path_and_the_lane_lint_passes` in merge/test_lane_lint.py, which pins today's not-run result. Until: 2026-11-21
