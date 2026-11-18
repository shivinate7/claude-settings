# Every repo runs the same kinds of checks

## The ruling

Owner, 2026-10-30 15:03 CDT, waiting item 87: every owner repo runs the same kinds of checks, judged by the same outcomes.

- Each kind of check looks at the same outcome in every repo.
- The number of checks scales with the repo's size. A bigger repo may run more checks, as long as each one looks at a shared outcome.
- Branch protection in every repo requires no status check (owner, 2026-11-15 19:08 CST, ruling `own-all-jobs-passed-removed`: "all jobs passed has been removed as a status requirement"). The `all-jobs-passed` rollup, from the shared action `actions/all-jobs-passed`, still runs. The repo's own checks run inside that rollup.
- Degen and ios-adblock already call the shared action in their CI.

Cites:

- Decision `uniform-over-variants` (a repo matches a shared format).
- Decision `main-branch-protection` (the required checks of main).

## Limits

- The rollup fails a job that failed, was cancelled or was skipped. The calling job must set `needs` and `if: always()`. Without `always()`, a skipped check reads as green.
- This repo's CI has the `all-jobs-passed` job, which calls the shared action `actions/all-jobs-passed`. Its `if` includes `always()`, and it runs on a ready pull request only. Branch protection requires no status check: the 2026-11-15 19:08 CST ruling removed the one check that the owner set on 2026-10-31 at 14:52 CDT (decision `main-branch-protection`, required checks of main). This record does not read the live setting.

Kind: process
Home: actions/all-jobs-passed/action.yml
