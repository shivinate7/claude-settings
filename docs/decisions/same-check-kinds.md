# Every repo runs the same kinds of checks

## The ruling

Owner, 2026-10-30 15:03 CDT, waiting item 87: every owner repo runs the same kinds of checks, judged by the same outcomes.

- Each kind of check looks at the same outcome in every repo.
- The number of checks scales with the repo's size. A bigger repo may run more checks, as long as each one looks at a shared outcome.
- Branch protection in every repo requires one check: the `all-jobs-passed` rollup, from the shared action `actions/all-jobs-passed`. The repo's own checks run inside that rollup.
- Degen and ios-adblock already call the shared action in their CI.

Cites:

- Decision `uniform-over-variants` (a repo matches a shared format).
- Decision `main-branch-protection` (the required checks of main).

## Limits

- The rollup fails a job that failed, was cancelled or was skipped. The calling job must set `needs` and `if: always()`. Without `always()`, a skipped check reads as green.
- This repo's CI has no `all-jobs-passed` job yet. Its branch protection is not read here, so its required checks are unmeasured.

Kind: process
Home: actions/all-jobs-passed/action.yml
