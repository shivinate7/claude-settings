# main branch protection

## The ruling, 2026-10-10

`main` of shivinate7/claude-settings has branch protection that the owner keeps as is. Measured on
2026-10-10 with `gh api repos/{owner}/{repo}/branches/main/protection`:

- A merge to `main` needs a pull request. The approval count is 0, so a PR needs no review.
- Force pushes and branch deletion are blocked.
- No status check is required. No CI check blocks a merge.
- Admins are exempt. The session account `shivinate7` is a repo admin.
- The repo has no rulesets.

Do not suggest required status checks. The agents' own rules govern every merge:
`rule:git-never-merge-failing-ci` and `rule:git-main-only-by-pr`.

## How to apply

Before every merge, read the checks yourself and refuse on red. Nothing in GitHub stops a red
merge. The `merge` tool reads its required checks from `.github/stamp.json`, because the
protection names none.
