# Every PR opens as a draft, and CI skips drafts

## The question

How do we run CI once per batch of reviewed changes, not once per push?

## The ruling

Owner rulings, 2026-10-10 and 2026-10-13. Every PR opens as a draft. CI skips draft PRs. Lane PRs
stay drafts. Only one integration PR per batch goes ready, and its run is the batch's only CI run
(CLAUDE.md rule `git-integration-branch-merge`).

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
  `cancel-in-progress: false`. Snippet 4 of skill ci-hygiene carries the same expression.
- Named limits: the gate does not judge a `gh api` POST to the pulls endpoint, or
  `hub pull-request`. Each can open a non-draft PR. A short-flag cluster such as `-dt x` is
  refused, a rare false alarm.
- The merge tool refuses a draft pull request in one line, before any claim or wait. It reads the
  draft state at the start and again at `--confirm`. Named limit: a pull request that turns draft
  during the wait is not stopped.

## The incident

2026-10-11, shivinate7/ios-adblock PR #61: `gh pr create --draft` then `gh pr ready` fired two
`pull_request` runs. The ready run 38159163245 was created at 17:19:32Z. The draft run
38159163645 was created at 17:19:33Z, carried draft=true, and skipped every job. The two runs
were in one group. Attempt 1 of the ready run was cancelled at 17:19:40Z, the second the draft
run ended. A re-run (attempt 2) then passed, so the run-level state reads success. Read
`attempts/1` to see a cancel. The risk remains for each repo that shares one PR group. A draft
run that arrives while a ready run is in progress cancels it. A pending ready run is replaced.

2026-10-10: 52 CI runs in this repo (UTC day). 7 were on the PR #313 branch, many on commits known to be red.

## Required checks on a skipped run

A job skipped by `if:` reports as passing (skill ci-hygiene, step 19). A draft needs no check,
because GitHub does not merge a draft. The GitHub docs say: "Draft pull requests cannot be merged."
(https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests).
Marking it ready fires `ready_for_review`. That run gets the same scoped range as a `synchronize`
run (`.github/scripts/harness-scope.sh`, line 13), not a full run.
main requires the `stamp.json` checks since 2026-10-12 (decision main-branch-protection,
the one home of required-check state). A skipped draft run satisfies each of them. The merge
tool refuses a head whose checks all skipped (decision merge-needs-a-proven-head).

- Unmeasured: that `ready_for_review` starts this workflow. It comes from GitHub's documented
  behavior, not from a run here.
- Unmeasured: the saving in runs.

Kind: process
Home: hooks/guard.py
