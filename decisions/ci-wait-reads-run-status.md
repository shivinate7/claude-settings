# CI waits read the run status

## The question

How do `bin/merge` and the CI-wake hook wait for a CI run to end, without using up the
GitHub API limit?

## The ruling

Owner, 2026-10-16 01:47 CDT: "Status read only." Neither program runs `gh run watch`. Each
one reads the run's status, at most once every 30 s, until the run ends or its deadline
passes.

- `merge/merge.py`, `block`: no watch. It pauses 30 s. The next pass of the wait loop reads
  the checks and runs, as it does now.
- `hooks/ci_wake.py`, `watch_run`: no watch. It reads `gh run view <id> --json status` once
  every 30 s, and returns when the status is `completed` or the deadline passes. A failed
  read ends the wait as unknown, as a failed watch does now.

## Why

MEASURED 2026-10-16 06:28 UTC: one `gh run watch` made 131 API calls in 60 s, on run
38861339728 (gates, in progress). That is about 7,900 calls an hour. The core limit is 5,000
an hour, shared by every session on the account. Calls by endpoint:

- 93 `check-runs/<id>/annotations`;
- 13 `actions/runs/<id>`;
- 13 `actions/workflows/<id>`;
- 12 `actions/runs/<id>/jobs`.

`gh run watch` refreshes every 3 s by default. Each refresh reads the annotations of every
finished job, so the count grows as jobs finish. Both programs threw that output away. Each
merge started one watcher and the CI-wake hook started another, on the same run.

On the night of 2026-10-15, merges failed on GitHub limits: PR 447 five times, and PRs in
another repo on the same account several times.

## Holes, named

- The secondary write limit on the lock commit is a separate limit. Its cause on this account
  is unmeasured. Debt `rate-retry-budget-short` (3 x 60 s is too short for GitHub's write
  limit).

Kind: build
