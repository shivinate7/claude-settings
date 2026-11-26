# CI speed is express: the suites bend, not the wait

## The ruling

Owner, 2026-11-13 11:34 CST and 11:36 CST, relayed by runner 10, the session that audited the merge path ("the suites bend, not the wait"; finding 2 of its blind audit): CI speed is express. A change that speeds CI sets no fixed time target. Its proof is a measure of the change itself.

- Step ci-cancel-on-close: when a PR closes or goes back to draft, `.github/workflows/cancel-on-close.yml` cancels that PR's unfinished runs. The proof is that a closed PR's run shows cancelled within the next minute. A draft return has the same proof, unmeasured: no live run has shown it yet. Its measure: 2,157 runner-minutes ran after a return to draft (REST read of the Nov 25 2026 CST day, of 40,747 checks.yml runner-minutes that day).
- GitHub lists no PR on the runs of a closed PR. So the script reads the PR's head branch and matches runs by it, never by the run's PR list (`.github/scripts/cancel_closed_pr_runs.py`, `select_runs`).
- An open PR's runs are cancelled only when it is a draft, and then only its `checks` runs created before the newest converted_to_draft event (`select_draft_runs`). Its other runs, and runs created at or after that event, keep going. An open ready PR loses nothing. It cancels nothing when another open PR shares the head branch. It never cancels a push run, a run on the default branch, a fork's run, or its own run.

Why: the run of batch 121, an integration PR that carried many lane PRs, went on 33 min after its PR closed and held the macOS slots. Later runs of other batches waited 3.4 to 10.4 min. A PR that went back to draft kept its ready run: checks.yml's concurrency group holds the draft flag, so the draft state cancelled nothing.

Kind: process
Home: .github/workflows/cancel-on-close.yml
