# main has no branch protection, by choice

## The ruling, 2026-09-24

`main` of shivinate7/claude-settings has no branch protection and no rulesets. No CI check
blocks a merge. The owner declined to add them. Do not suggest them again.

The reason: the agents' own rules are enough here. `rule:git-never-merge-failing-ci` and
`rule:git-main-only-by-pr` govern every merge.

## How to apply

Before every merge, read `gh pr checks` yourself and refuse on red. Nothing else stops a
red merge. The session account `ssemwal-cdc` is not a repo admin, so it cannot change
protection.
