# Batch CI's macOS jobs run on the owner's Mac

## The ruling

Owner, Nov 12 14:19 CST, pick e (restart-plan R58, on the record branch restart-plan):

- An integration PR's CI run (head branch `batch-*`) runs its macOS jobs on the owner's Mac (runner label `claude-settings-mac`) when that runner is online. Otherwise they run on `macos-latest`.
- No fork PR runs on the Mac: its macOS jobs run on `macos-latest`.
- lane-touched-tests' macOS job skips while a `checks` run on a `batch-*` branch is queued or in progress. An unknown read keeps the job.

Mechanism:

- The scope job's `Pick the macOS runner` step (`.github/scripts/mac-runner.py`) writes `mac_runner`. Each macOS job's `runs-on` tests for a fork PR first and gives it `macos-latest`; only a same-repo run reads `mac_runner`. An unknown runners read picks `macos-latest`.
- lane-touched-tests' skip step runs `.github/scripts/batch-macos-skip.py`.
- Secret `MAC_RUNNER_READ_TOKEN` (reads the repo's runners list) is owner-added. Without it, every macOS job runs on `macos-latest`.

Limits:

- A Mac that goes offline after the pick leaves its jobs queued, up to a day, until GitHub drops them.
- The fork gate is each `runs-on`'s fork test. A pull_request run reads the PR's own workflow file, so the gate holds while that file is ours. The real boundary is GitHub's fork-run approval and the runner's repo scope (unverified here).
- `mac-runner.py` runs in the scope job on `ubuntu-latest`. The steps of the three macOS jobs, which are same-repo `batch-*` code, run on the owner's Mac. They share the one runner and run in series.
- The `batch-` prefix is in `ci-scope.sh`, `mac-runner.py`, `batch-macos-skip.py` and the `lane-touched-tests` selector. Each script is a standalone step, so each keeps a copy; one home is unbuilt.
- While a batch `checks` run is busy (a queued Mac job keeps it busy for up to a day, see the first limit), a lane's draft run has no macOS row, and the lane lint reads a missing macOS row as a pass (`draft_run_state` in `merge/merge.py`). A macOS-only failure in a lane can pass `merge --lane-lint` and show later, in the batch's own macOS run, with no bound on how much later. Accepted (coordinator pick, 2026-11-14 11:04 CST, undoable); debt `lane-lint-macos-row-skipped`.
- `lane-touched-tests` gives `github.token` to the skip step, and `checks.yml` gives `MAC_RUNNER_READ_TOKEN` to `mac-runner.py`, both from PR-head code, against the rule in the comment above its `Reach the merge base` step ("the step that runs the PR's code gets none"). Same-repo writers already control the workflow and its secrets, so they gain nothing. A fork PR's run gets `github.token` read-only in the skip step and no secret. Open owner call: move the skip script out of PR code, or accept this.

Why: restart-plan R58 holds the owner's reasons.

- Check: `lint/test_windows_split.py` (the `runs-on` string, `mac-runner.py`'s pick, and `batch-macos-skip.py`).
- Cost: at most one runners-list read per checks run on a same-repo batch-* pull request, and at most two `gh api` reads per draft lane-touched-tests run. At most one python start per script, and no file written except `$GITHUB_OUTPUT` and, on a failed runners read, `$GITHUB_STEP_SUMMARY`, no timer.

Kind: process
Home: .github/scripts/mac-runner.py
