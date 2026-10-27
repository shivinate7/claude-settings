# main branch protection

## The ruling

`main` of shivinate7/claude-settings requires the eleven checks that `.github/stamp.json`
`merge.requiredChecks` names: scope, checks, checks-windows, checks-windows-guard, checks-mutate-guard,
checks-windows-merge, checks-windows-rest, checks-macos, shell-macos, pointer-windows, checks-shoot.

- A merge needs a pull request and no approval.
- `strict` is false: GitHub merges a PR that lacks main's newest commit. The `merge` tool refuses it (`merge-needs-current-base`, a merge needs a green run on the current base).
- Admins are included (`enforce_admins`), so the rule binds the owner.
- Force pushes and branch deletion are blocked. The repo has no rulesets.
- The contexts copy `stamp.json` `merge.requiredChecks`. Change both when a job is renamed or added.
- The PUT is `gh api -X PUT repos/shivinate7/claude-settings/branches/main/protection --input <json>`.
  A PUT replaces the whole rule, so the input carries every field. It needs the owner's login:
  `ssemwal-cdc` has push, not admin.
- Before every merge, read the checks yourself and refuse on red. The `merge` tool reads its checks
  from `stamp.json`.

Reason: agent rules alone did not stop red merges.

Kind: process
Home: .github/stamp.json
