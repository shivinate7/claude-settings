# CI cuts in steps, and step 3 runs at milestones

## The ruling

Owner, 2026-10-27 12:07 CDT (waiting page item 31, pick e), roadmap step c95: trust first, then cut CI in steps. Each step starts only past its measured bar. A miss sends the step back.

- Step 1: the full run is trustworthy. Red means broken, not out of time. It landed in batch #725 (main 0fb91de, Oct 28). Its job caps follow `ci-job-caps`.
- Step 2: quick checks on each branch, and the full suite on main. This is the shape of q_max's CI. Its bar is in `ci-step2-bar`. Step 2 stays off in claude-settings.
- Step 3: milestone runs. The full suite runs at milestones, not on every merge. A milestone is a set number of app batches or a named milestone. A red run blocks the next merge until it is fixed. The owner restated this on Nov 2 (closed item `swift-tests-ci`, see `swift-tests-at-milestones`). Step 3 is its own step, c95-milestone-runs, which holds its bar.

Premise: no GitHub Actions minutes are billed to claude-settings. The owner confirmed this on Oct 28 13:23 CDT (waiting page item 38, pick a). Its cost is $0 here.

Part 2 of step c95 (PR #896) merged Oct 31 (main d657e1da). Step 3's bar is measured after that. It is not set in this record.

Kind: process
Home: .github/workflows/checks.yml
