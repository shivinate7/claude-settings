# The merge tool's revert push cancels a running CI run

- **What.** `wait_checks` returns on the first red check while other jobs still run. The fail path then pushes the revert, which cancels that run. This breaks `git-integration-branch-merge` (never push to a ready PR while its CI runs).
- **Where.** `merge/merge.py`, `revert_claim` (called from `fail`).
- **Decision.** `draft-until-reviewed` (every PR opens as a draft; only the integration PR goes ready and runs CI).
- **Retire.** The tool waits for every check to finish before the revert push, and a case pins it.
