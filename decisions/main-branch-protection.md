# main branch protection

## The ruling

`main` of shivinate7/claude-settings requires the ten checks that `.github/stamp.json`
`requiredChecks` names: scope, gates, gates-windows, gates-windows-guard, gates-mutate-guard,
gates-windows-merge, gates-windows-rest, gates-macos, shell-macos, pointer-windows.

- A merge needs a pull request. Approvals: 0.
- `strict` is false: a PR need not carry main's newest commit.
- Admins are included (`enforce_admins`), so the rule binds the owner.
- Force pushes and branch deletion are blocked. The repo has no rulesets.
- The contexts copy `stamp.json` `requiredChecks`. Change both when a job is renamed or added.
- The PUT is `gh api -X PUT repos/shivinate7/claude-settings/branches/main/protection --input <json>`.
  A PUT replaces the whole rule, so the input carries every field. It needs the owner's login:
  `ssemwal-cdc` has push, not admin.
- Before every merge, read the checks yourself and refuse on red. The `merge` tool reads its checks
  from `stamp.json`.

Reason: agent rules alone did not stop red merges (merge-needs-a-proven-head, no merge on an
unproven head).

## Limits

- A skipped job counts as passing. A draft run that skips satisfies every required check. The
  merge tool refuses that head (merge-needs-a-proven-head); GitHub does not.
- `strict` is false, so a PR green on an old base can merge over a newer main. The merge tool's
  read and CI on main after the push cover this.

Kind: process
Home: .github/stamp.json
