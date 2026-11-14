# Every repo runs the same kinds of checks

## The ruling

Owner, 2026-10-30 15:03 CDT, waiting item 87: every owner repo runs the same kinds of checks, judged by the same outcomes.

- Each kind of check looks at the same outcome in every repo.
- The number of checks scales with the repo's size. A bigger repo may run more checks, as long as each one looks at a shared outcome.
- Branch protection in every repo requires one check: the `all-jobs-passed` rollup, from the shared action `actions/all-jobs-passed`. The repo's own checks run inside that rollup.
- Degen and ios-adblock already call the shared action in their CI.
- A repo with no CI gets a starter CI, not an exemption (owner, 2026-11-10 16:25 and 16:36 CST; restart plan R17). Skill project-ops writes it from `skills/project-ops/templates/starter-ci/checks.yml` (decision `opt-in-ci-templates-composite`). A lane lint of a head with no workflow file refuses, and no flag lifts its no-CI stop, which names the starter step. For a PR number, a draft-run stop that a `--lint-unknown-ok` reason lifts comes first (the notes entry `no-ci-lift-before-starter-step`). In a protected repo, a merge of such a head refuses: its required check reads pending, since no run reports it. The merge names no starter step (merge/merge.py `confirm`, `head_not_green`).

Cites:

- Decision `uniform-over-variants` (a repo matches a shared format).
- Decision `main-branch-protection` (the required checks of main).

## Limits

- The rollup fails a job that failed, was cancelled or was skipped. The calling job must set `needs` and `if: always()`. Without `always()`, a skipped check reads as green.
- This repo's CI has the `all-jobs-passed` job, which calls the shared action `actions/all-jobs-passed`. Its `if` includes `always()`, and it runs on a ready pull request only. Branch protection requires that one check: the owner set it on 2026-10-31 at 14:52 CDT, and the coordinator's read-back showed it (decision `main-branch-protection`, required checks of main). This record does not read the live setting.

Kind: process
Home: actions/all-jobs-passed/action.yml
