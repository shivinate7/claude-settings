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

## Claude's own waits

Owner, 2026-10-16 03:00 CDT: "Change them too." Claude and its agents do not run
`gh run watch` either, in the foreground or the background. A session waits on CI through
the CI-wake hook or `bin/merge`. Lane own-ci-wait changes the guard's remedy text in
hooks/guard_stream.py and the two guides that name the watch (skills/ci-hygiene,
agents/test-author.md).

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

- The secondary limit is a separate limit. GitHub's docs give it a per-minute cap on REST
  calls, which watchers from several sessions can pass together. On 2026-10-16 06:51 UTC a
  call got "API rate limit exceeded" while core had 4,560 of 5,000 left. That watchers cause
  it is unmeasured. Debt `rate-retry-budget-short` (3 x 60 s is too short for GitHub's write
  limit).
- `ci_wake.wait_for` lists the head's runs once. A run that starts after that list is never
  judged, so the hook can print green while that run goes on. This gap is older than this
  change. `bin/merge` lists the runs again on each pass. Debt `ci-wake-lists-runs-once` (a
  later run is not judged).
- A merge wait now reads the checks and runs every 30 s, not every 60 s: about 6 calls a
  minute. Unmeasured on a real run.

Kind: build
