# Every PR opens as a draft, and CI skips drafts

## The question

How do we run CI once per reviewed change, not once per push?

## The ruling

Owner ruling, 2026-10-10. Every PR opens as a draft. CI skips draft PRs. The orchestrator marks a
PR ready, or folds it into an integration branch, only after review.

- Guard gate `draft-pr` refuses `gh pr create` without `--draft` or `-d`, also inside `sh -c` scripts and command substitutions. The last
  `--draft`, `-d` or `--draft=X` wins.
- `gates.yml` runs on `opened`, `synchronize`, `reopened` and `ready_for_review`. The `scope` job
  skips when the PR is a draft. Each other job needs `scope`, so each skips too.
- Push to main, schedule and manual runs are unchanged.
- Named limits: the gate does not judge a `gh api` POST to the pulls endpoint, or
  `hub pull-request`. Each can open a non-draft PR.
- The merge tool does not check for a draft yet. That check comes in a later PR.

## The incident

2026-10-10: 52 CI runs in this repo (UTC day). 7 were on the PR #313 branch, many on commits known to be red.

## Required checks on a skipped run

A job skipped by `if:` reports as passing (skill ci-hygiene, step 11). A draft needs no check,
because GitHub does not merge a draft: "Draft pull requests cannot be merged." (GitHub docs, about
pull request merges). Marking it ready fires `ready_for_review`. That run gets the same scoped
range as a `synchronize` run (`.github/scripts/harness-scope.sh`, lines 9 to 11), not a full run.
Measured in decision main-branch-protection: main requires a PR (0 approvals). It blocks force
pushes and deletion. It requires no status checks, exempts admins, and has no rulesets. So no
check is required, and a skipped draft run blocks nothing.

- Unmeasured: that `ready_for_review` starts this workflow. It comes from GitHub's documented
  behavior, not from a run here.
- Unmeasured: the saving in runs.
