# Lane lint skips the guard suite's browser deny cases

**What.** `merge --lane-lint` runs `hooks/test_guard.py` after `actions/playwright-setup/install.sh local` (npm ci and the pin), so the suite reads `PASS` or `FAIL`. Lane lint downloads no browser (decision `playwright-install-once`). With the pinned browser absent or not launching, ci-job unsets `GUARD_CHROMIUM` and the suite skips the page-item-design deny cases in `hooks/test_guard.py`. One printed line names them and says CI runs them. A lane that breaks only those cases passes lane lint and goes red in batch CI. Claude is likely to hit it, since any lane that edits the page-item-design checker in `hooks/guard.py` picks that suite.

**Where.** `hooks/test_guard.py` (the `GUARD_CHROMIUM` marker), `BROWSER_MARKERS` in `lint/workflow_steps.py`, and `bin/ci-job` (`prepare_setup`).

**Decision.** `playwright-install-once`, one Playwright install, never from an agent. Also `lanes-run-no-full-ci-job`, the lane lint runs the picked suites and not the full CI job.

**Retire.** The pinned browser reaches the box that runs lane lint without an agent downloading it, or the checker's deny cases run without a browser. Lane lint then runs those cases and the skip line goes. Proof: the browser-absent case of `merge/test_lane_lint_guard_suite.py` is rewritten to expect the marker set.

Fix: step `guard-browser-once`, doing in lane lane-lint-guard-suite-install: the orchestrator installs the pinned Chromium once per box (decision playwright-install-once), so lane lint launches it. Until: 2026-11-21
