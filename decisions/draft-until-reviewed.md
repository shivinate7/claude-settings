# Every PR opens as a draft, and CI skips drafts

## The question

How do we run CI once per reviewed change, not once per push?

## The ruling

Owner ruling, 2026-10-10. Every PR opens as a draft. CI skips draft PRs. The orchestrator marks a
PR ready, or folds it into an integration branch, only after review.

- Guard gate `draft-pr` refuses `gh pr create` without `--draft` or `-d`, also inside `bash -c`.
- `gates.yml` runs on `opened`, `synchronize`, `reopened` and `ready_for_review`. The `scope` job
  skips when the PR is a draft. Each other job needs `scope`, so each skips too.
- Push to main, schedule and manual runs are unchanged.

## The incident

2026-10-10: 46 CI runs in this repo. 6 were for PR #313, many on commits known to be red.

## Required checks on a skipped run

A job skipped by `if:` reports as passing (skill ci-hygiene, step 11). A draft needs no check,
because GitHub does not merge a draft. Marking it ready fires `ready_for_review`, so the full run
starts before any merge. The `scope` job stays the one required check, as in decision
ci-wall-time-cuts, cut B.

- Unmeasured: that GitHub refuses to merge a draft, and that `ready_for_review` starts this
  workflow. Both come from GitHub's documented behavior, not from a run here.
- Unmeasured: the saving in runs.
