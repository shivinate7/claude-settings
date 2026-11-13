# CI speed is express: the suites bend, not the wait

## The ruling

Owner, 2026-11-13 11:34 CST and 11:36 CST, via runner 10 ("the suites bend, not the wait"; source: runner 10's blind audit of the merge path, finding 2): CI speed is express. A change that speeds CI sets no fixed time target. Its proof is a measure of the change itself.

- Step ci-cancel-on-close: when a PR closes, `.github/workflows/cancel-on-close.yml` cancels that PR's unfinished runs. The proof is that a closed PR's run shows cancelled within the next minute.
- It never cancels a run of a PR that is still open, nor a push run on main (`.github/scripts/cancel_closed_pr_runs.py`, `select_runs`).

Why: batch 121's run went on 33 min after its PR closed and held the macOS slots. Later runs of other batches waited 3.4 to 10.4 min.

Kind: process
Home: .github/workflows/cancel-on-close.yml
