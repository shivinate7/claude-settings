# Batch CI's macOS jobs run on the owner's Mac

## The ruling

Owner, Nov 12 14:19 CST, pick e (restart-plan R58, on the record branch restart-plan):

- An integration PR's CI run (head branch `batch-*`) runs its macOS jobs on the owner's Mac (runner label `claude-settings-mac`) when that runner is online. Otherwise they run on `macos-latest`.
- A fork PR never reaches the Mac: its macOS jobs run on `macos-latest`.
- lane-touched-tests' macOS job skips while a `checks` run on a `batch-*` branch is queued or in progress. An unknown read keeps the job.

Mechanism:

- The scope job's `Pick the macOS runner` step (`.github/scripts/mac-runner.py`) writes `mac_runner`. Each macOS job's `runs-on` reads it, and a fork PR's run reads `macos-latest` before it. An unknown runners read picks `macos-latest`.
- lane-touched-tests' skip step runs `.github/scripts/batch-macos-skip.py`.
- Secret `MAC_RUNNER_READ_TOKEN` (reads the repo's runners list) is owner-added. Without it, every macOS job runs on `macos-latest`.

Limits:

- A Mac that goes offline after the pick leaves its jobs queued, up to a day, until GitHub drops them.

Why: restart-plan R58 holds the owner's reasons.

- Check: `lint/test_windows_split.py` (the `runs-on` string, `mac-runner.py`'s pick, and `batch-macos-skip.py`).
- Cost: one runners-list read per checks run, and two `gh api` reads per lane-touched-tests run (unmeasured). No process starts, no file written, no timer.

Kind: process
Home: .github/scripts/mac-runner.py
