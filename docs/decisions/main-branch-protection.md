# main branch protection

## The ruling

`main` of shivinate7/claude-settings requires one check: `all-jobs-passed`, the fan-in job in
`.github/workflows/checks.yml` that runs the shared action `actions/all-jobs-passed`. Owner ruling,
2026-10-30 15:03 CDT (waiting-page item 87, record same-check-kinds): every repo requires that one check.
`.github/stamp.json` `merge.requiredChecks` is `"protection"`, so the `merge` tool reads the name from the
protection. GitHub's branch protection setting is the owner's to change.

- `all-jobs-passed` needs every job that runs on a pull request. It fails when a needed job failed, was
  cancelled or was skipped. `lint/test_all_jobs_passed.py` goes red when a job that runs on a pull request is
  missing from its `needs`.
- A job that a scope flag turns off skips its steps, not the job, so it ends green, not skipped.
- A draft PR runs no CI: `scope` skips on a draft, and every other job skips with it.
- A merge needs a pull request and no approval.
- `strict` is false: GitHub merges a PR that lacks main's newest commit. The `merge` tool refuses it (`merge-needs-current-base`, a merge needs a green run on the current base).
- Admins are included (`enforce_admins`), so the rule binds the owner.
- Force pushes and branch deletion are blocked. The repo has no rulesets.
- The protection holds the one required check. A new job goes in the `needs` of `all-jobs-passed`, not in
  the protection. A repo that pins a list in `stamp.json` instead has `merge` refuse the run when the pinned
  list and a non-empty protection disagree, and name both sets (c189).
- The switch changes only the required checks:
  `gh api -X PATCH repos/shivinate7/claude-settings/branches/main/protection/required_status_checks`
  with `strict=false` and one check, `all-jobs-passed`, app id 15368 (GitHub Actions). It needs the owner's
  login: `ssemwal-cdc` has push, not admin.
- Before every merge, read the checks yourself and refuse on red. The `merge` tool reads its checks
  from the branch protection.
- Owner ruling, 2026-10-28 (waiting-page item 33 a): a rename of required checks switches branch
  protection in the merge act. The owner switches it, then the batch merges at once.

Reason: agent rules alone did not stop red merges.

Kind: process
Home: .github/stamp.json
