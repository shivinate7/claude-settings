# CI speed is express: the suites bend, not the wait

## The ruling

Owner, 2026-11-13 11:34 CST and 11:36 CST, relayed by runner 10, the session that audited the merge path ("the suites bend, not the wait"; finding 2 of its blind audit): CI speed is express. A change that speeds CI sets no fixed time target. Its proof is a measure of the change itself.

- Step ci-cancel-on-close: when a PR closes, `.github/workflows/cancel-on-close.yml` cancels that PR's unfinished runs. The proof is that a closed PR's run shows cancelled within the next minute.
- GitHub lists no PR on the runs of a closed PR, so the script matches runs by the PR's head branch, read from the PR, and not by the run's PR list (`.github/scripts/cancel_closed_pr_runs.py`, `select_runs`).
- It never cancels a run of a PR that is still open: it cancels nothing when another open PR shares the head branch. It never cancels a push run, a run on the default branch, a fork's run, or its own run.

Why: the run of batch 121, an integration PR that carried many lane PRs, went on 33 min after its PR closed and held the macOS slots. Later runs of other batches waited 3.4 to 10.4 min.

Kind: process
Home: .github/workflows/cancel-on-close.yml
