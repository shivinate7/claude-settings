# A non-draft PR that is red and idle for 2 hours returns to draft

## The ruling

Owner ruling R6, typed 2026-11-23 10:54 CST. It says:

- A non-draft PR whose CI is red, and that had no push for 2 hours, returns to draft.
- The merge tool drafts it on demand when it clashes with a PR going ready.
- The janitor's daily sweep drafts it too.
- A PR comment says why, and wakes the session that watches the PR.
- Undo is `gh pr ready N`.

## What the code does

The rule is in `merge/idle_prs.py`. It judges one open PR that is not a draft.

- Red: the head's checks read red. A run still going on the head keeps the PR ready.
- Age: the time since the newest run of the head with the event `pull_request` was created. Runs with other events do not count.
- Two hours (7200 seconds) or more drafts the PR. Less keeps it ready.
- Clock: GitHub's clock, read from the Date header of the newest GitHub reply the host read. The local clock is never used. With no GitHub clock read, the PR is unknown and stays ready.
- Unknown, and left as it is: a failed read, a run with no readable time, or a row with no draft field.
- Drafting is `gh pr ready <n> --undo` on a computer. A cloud session cannot draft that way. It gets the route the merge tool prints, sends nothing, and the PR stays unknown.
- One comment per drafted PR. It names the head, the red jobs, the hours idle, the ruling, and the way back: fix the failing job, push, and run `merge <n> --ready`.
- A draft that lands before a failed comment is reported as "drafted, comment failed". Nothing is retried.

## Callers

- `merge --draft-idle` sweeps every open PR. The janitor's daily sweep runs it once for each repository whose origin is on github.com. It does not run at SessionEnd or past the sweep's deadline. A preview prints `WOULD run` and drafts nothing. The run has a 300-second timeout. A failed run prints its own unknown line and does not change the sweep's exit code.
- The pre-ready clash of `merge <n> --ready` drafts a counted clash that is an idle red PR, then reads that PR as a report line, not a fail. Every other read of that PR leaves the clash counted: keep, unknown, a cloud route that cannot draft, or an unread GitHub clock. The read-only `--fast-checks` run reads the clash and never drafts.

## Cost

Cost: each sweep reads the open PR list once (`CostHost`, pinned in `merge/test_idle_prs.py`). A non-draft PR costs three GitHub calls (`CostHost`, pinned in `merge/test_idle_prs.py`) when required checks are read, and one call when they are not (`CostHost`, pinned in `merge/test_idle_prs.py`). A drafted PR costs one ready-undo call and one comment (`CostHost`, pinned in `merge/test_idle_prs.py`). Each repository the janitor sweeps costs one git read and one merge process (`DraftIdlePassTests`, pinned in `janitor/test_sweep.py`). Unmeasured: a draft also fires the `converted_to_draft` event, which starts the touched-tests workflow.

## Why

The ruling names the outcome, not a reason. A red PR that nobody pushed to for two hours stops counting as ready in a clash, and the session that watches it is told why.

## Undo

The ruling's undo is `gh pr ready N`. The comment names `merge N --ready` as the way back. Both mark the PR ready. The record holds both.

## Limits

- A person readies the PR again with no push, while it is red and idle. The next sweep drafts it again and posts a second comment. Note `idle-red-reready-comments-twice`.
- The sweep also drafts fork, other-author and release-base PRs. The ruling names no exclusion. Dependabot is the likely other-author case. Note `idle-sweep-no-author-filter`.
- A cloud session drafts by MCP, which posts no comment, so the session that watches the PR is not woken. Debt `idle-cloud-mcp-draft-silent`.

Kind: process
Home: merge/idle_prs.py
