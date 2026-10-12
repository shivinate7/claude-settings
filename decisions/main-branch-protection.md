# main branch protection

## The ruling, 2026-10-12

`main` of shivinate7/claude-settings requires the ten checks that `.github/stamp.json`
`requiredChecks` names. MEASURED 2026-10-12 with
`gh api repos/{owner}/{repo}/branches/main/protection`, right after the owner's PUT:

- A merge to `main` needs a pull request. The approval count is 0, so a PR needs no review.
- Required status checks: scope, gates, gates-windows, gates-windows-guard,
  gates-mutate-guard, gates-windows-merge, gates-windows-rest, gates-macos, shell-macos,
  pointer-windows. `strict` is false: a PR need not carry main's newest commit.
- Admins are included (`enforce_admins`). `shivinate7` is the repo admin, so the rule
  binds the owner too.
- Force pushes and branch deletion are blocked. Linear history, signatures, conversation
  resolution and branch lock are off.
- The repo has no rulesets.

The 2026-10-10 ruling said: do not suggest required status checks. Two incidents changed
it. 14 merges landed on red on 2026-10-11. A merge landed on an all-skipped head on
2026-10-12 (decision merge-needs-a-proven-head). The agents' rules alone did not hold.

The protection's contexts are a copy of `stamp.json` `requiredChecks`. When a job is
renamed or added, change both. The PUT is
`gh api -X PUT repos/shivinate7/claude-settings/branches/main/protection --input <json>`.
A PUT replaces the whole rule, so the input carries every field. The owner's login is
needed: `ssemwal-cdc` has push, not admin.

## What the rule does not catch

- A skipped job counts as passing. A run skipped as a draft satisfies every required
  check. The merge tool refuses that head (decision merge-needs-a-proven-head); GitHub
  does not.
- `strict` is false, so a PR green on an old base can merge over a newer main. The merge
  tool's own read, and CI on main after the push, cover this.

## How to apply

Before every merge, read the checks yourself and refuse on red. The `merge` tool reads its
required checks from `.github/stamp.json`. The protection mirrors that list. It now blocks
a red merge through the GitHub UI and the API too.
