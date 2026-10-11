# Every PR opens as a draft, and CI skips drafts

## The question

How do we run CI once per reviewed change, not once per push?

## The ruling

Owner ruling, 2026-10-10. Every PR opens as a draft. CI skips draft PRs. The orchestrator marks a
PR ready, or folds it into an integration branch, only after review.

- Guard gate `draft-pr` refuses `gh pr create` without `--draft` or `-d`. It reads `sh -c`
  scripts, command substitutions and subshells. The last `--draft`, `-d` or `--draft=X` wins.
  A value is true only in gh's ParseBool true set (1, t, T, TRUE, true, True).
- The gate also refuses the MCP tool `mcp__github__create_pull_request` unless its input has
  `draft: true`.
- `gates.yml` runs on `opened`, `synchronize`, `reopened` and `ready_for_review`. The `scope` job
  skips when the PR is a draft. Each other job needs `scope`, so each skips too.
- Push to main, schedule and manual runs are unchanged.
- The `concurrency` group holds the PR draft state (`format('{0}-{1}', github.ref, github.event.pull_request.draft)`).
  A draft run then replaces only draft runs, and a ready run only ready runs. Turning off cancel for
  drafts is not enough: GitHub keeps one pending run per group and replaces it even with
  `cancel-in-progress: false`. Skill ci-hygiene, step 4 and snippet 4, carry the same expression.
  Orchestrator ruling, 2026-10-11.
- Named limits: the gate does not judge a `gh api` POST to the pulls endpoint, or
  `hub pull-request`. Each can open a non-draft PR. A short-flag cluster such as `-dt x` is
  refused, a rare false alarm.
- The merge tool refuses a draft pull request in one line, before any claim or wait. It reads the
  draft state at the start and again at `--confirm`. Named limit: a pull request that turns draft
  during the wait is not stopped.

## The incident

2026-10-11, shivinate7/ios-adblock PR #61: `gh pr create --draft` then `gh pr ready` fired two
`pull_request` runs, 1 second apart (17:19:32Z run 38159163245, 17:19:33Z run 38159163645). The
later one carried draft=true and skipped every job (read: conclusion skipped). It was in the same
group, so it cancelled the ready run through `cancel-in-progress`. Measured today: run 38159163245
reads success, not cancelled, so the cancel is not seen in the run state now (maybe re-run).
Unmeasured: the order of the `ready_for_review` run.

2026-10-10: 52 CI runs in this repo (UTC day). 7 were on the PR #313 branch, many on commits known to be red.

## Required checks on a skipped run

A job skipped by `if:` reports as passing (skill ci-hygiene, step 19). A draft needs no check,
because GitHub does not merge a draft. The GitHub docs say: "Draft pull requests cannot be merged."
(https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests).
Marking it ready fires `ready_for_review`. That run gets the same scoped range as a `synchronize`
run (`.github/scripts/harness-scope.sh`, lines 13 to 14), not a full run.
Measured in decision main-branch-protection: main requires a PR (0 approvals). It blocks force
pushes and deletion. It requires no status checks, exempts admins, and has no rulesets. So no
check is required, and a skipped draft run blocks nothing.

- Unmeasured: that `ready_for_review` starts this workflow. It comes from GitHub's documented
  behavior, not from a run here.
- Unmeasured: the saving in runs.
