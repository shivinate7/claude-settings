# CI cuts in steps, checks steps keep running, Windows base jobs follow scope

## The ruling

Owner, 2026-10-27 12:07 CDT (waiting page item 31, pick e), roadmap step c95: trust first, then cut CI in steps. Each step starts only past its measured bar. A miss sends the step back.

- Step 1: the full run is trustworthy. Red means broken, not out of time. It landed in app batch #725 (main commit 0fb91de, Oct 28). Its job caps follow `ci-job-caps`.
- Step 2: quick checks on each branch, and the full suite on main. This is the CI shape of q_max. Its bar is in `ci-step2-bar`. Step 2 stays off in claude-settings.
- Step 3: milestone runs. The full suite runs at milestones, not on every merge. A milestone is a set number of app batches or a named milestone. The owner restated this on Nov 2 (closed item `swift-tests-ci`, see `swift-tests-at-milestones`). Step 3 is its own step, c95-milestone-runs, which holds its bar.
- Part 2 of step c95 (pull request #896) merged Oct 31 (main commit d657e1da). Step 3's bar is measured after that. It is not set in this record.

Process-only (coordinator, 2026-11-01 22:25 CST): a red run blocks the next merge until it is fixed.

Premise: no GitHub Actions minutes are billed to claude-settings. The owner confirmed this on Oct 28 13:23 CDT (waiting page item 38, pick a). Its cost is $0 here.

Kind: process
Home: .github/workflows/checks.yml

## R3: checks steps keep running after a failure

Owner, 2026-11-23 10:49 CST, "go", on the plan route.

- In the `checks` job, every step after setup carries `!cancelled()`, combined with its own `if` where it has one.
- A failed step stops none of the later steps. The job ends red, with each red step shown.
- Exempt: the checkout and setup-python steps. They carry no guard.

R3 is a process ruling.
Home: .github/workflows/checks.yml

## R4a: Windows base jobs on a pull request run with their scope flag

Owner, 2026-11-23 10:28 and 10:49 CST, option a.

- On a pull request, the base Windows jobs run their steps only when their scope flag is set: `windows_guard` for the guard slice, and `checks_windows_merge`, `checks_windows_rest`, `checks_windows_rest_2` for the others. The narrow rule sets them, in the scope script `ci-scope.sh`. The 13 Windows shard jobs do not run on a pull request (decision `windows-prs-run-marked-tests`).
- Scheduled and dispatched runs set every Windows flag, so they run every Windows step, shards included. They are the net.
- Known gap: none for the daily skip. A push after the green daily makes the daily run every Windows shard.
- Measure (consultant, 13:26 CST, not a ruling): on the last 40 merged pull requests (3764 to 3813), the merge flag was set on 18 under the narrow rule, against 29 by imports.

R4a is a process ruling.
Home: .github/scripts/ci-scope.sh
