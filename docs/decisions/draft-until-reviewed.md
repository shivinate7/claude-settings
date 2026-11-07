# Every PR opens as a draft, and CI skips drafts

## The ruling

Owner, 2026-10-10 and 2026-10-13: every PR opens as a draft, and CI skips draft PRs. Lane PRs stay drafts. Only one integration PR per batch goes ready, and its run is the batch's only CI run (`git-integration-branch-merge`).

- Guard rule `draft-pr` refuses a create that is not a draft. For `gh pr create` that is a call without `--draft` or `-d`; it reads `sh -c` scripts, command substitutions and subshells. The last `--draft`, `-d` or `--draft=X` wins. A value is true only in gh's ParseBool true set (1, t, T, TRUE, true, True). For the MCP tool `mcp__github__create_pull_request` it is an input without `draft: true`.
- The same rule asks before a ready mark in a lane session: `gh pr ready <pr>`, or the MCP tool `mcp__github__update_pull_request` with `draft: false`. It passes when the pull request is the batch's integration PR, shown by the `batch` label or a head ref that starts with `batch-` (one REST read of the pull request gives both), or when the session carries no `cs-build:lane` tag. A failed read asks. `--undo` and `-h` pass (owner ruling 2026-11-07 13:20 CST, decision `cull-rules`; coordinator ruling 2026-11-07 14:12 CST).
- `checks.yml` runs on `opened`, `synchronize`, `reopened` and `ready_for_review`. The `scope` job skips when the PR is a draft. Each other job needs `scope`, so each skips too. Push to main, schedule and manual runs are unchanged.
- The `concurrency` group holds the PR draft state (`format('{0}-{1}', github.ref, github.event.pull_request.draft)`), so a draft run replaces only draft runs and a ready run only ready runs. Turning off cancel for drafts is not enough: GitHub keeps one pending run per group and replaces it even with `cancel-in-progress: false`. Snippet 4 of skill ci-hygiene carries the same expression.
- The merge tool never merges a draft pull request. On a draft, `--confirm` is the records page step and stops before any claim, wait or merge (`records-index-at-merge`). It reads the draft state at the start and again under the merge lock.
- A job skipped by `if:` reports as passing, unless an `all-jobs-passed` rollup needs it (skill ci-hygiene, "Before you skip a required job"). A draft needs no check, because GitHub does not merge a draft. Marking it ready fires `ready_for_review`, with the same scoped range as a `synchronize` run (`.github/scripts/ci-scope.sh`). A skipped draft run satisfies each required check (`main-branch-protection`, the one home of required-check state). The merge tool refuses a head whose checks all skipped.

Why: a draft run that arrives while a ready run is in progress cancels it, and a pending ready run is replaced. Pushes to a PR branch also spent CI on commits known to be red.

Limits:

- The guard does not judge a `gh api` POST to the pulls endpoint, or `hub pull-request`. Each can open a non-draft PR.
- The guard does not judge a REST PATCH with `draft: false` or a `gh api graphql` call. REST takes no draft field; ready is the GraphQL mutation `markPullRequestReadyForReview`, so the command and MCP forms above are the routes it reads.
- A lane session whose own `get_session` record is unread counts as no lane, as for `load-brake`, so its ready mark passes.
- A short-flag cluster such as `-dt x` is refused, a rare false alarm.
- A pull request that turns draft during the merge wait is not stopped.
- Unmeasured: that `ready_for_review` starts this workflow (it comes from GitHub's documented behavior), and the saving in runs.

Kind: process
Home: hooks/guard.py
