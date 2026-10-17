# CI waits read the run status

## The ruling

Owner, 2026-10-16 01:47 CDT ("Status read only") and 03:00 CDT ("Change them too"): no program and no agent runs `gh run watch`, in the foreground or the background. Each wait reads the run's status at most once every 30 s, until the run ends or its deadline passes.

- `merge/merge.py`, `block`: no watch. It pauses 30 s. The next pass of the wait loop reads the checks and runs.
- `hooks/ci_wake.py`, `watch_run`: no watch. It reads `gh run view <id> --json status` once every 30 s, and returns when the status is `completed` or the deadline passes. A failed read gets one retry after the 30 s pause, never past the deadline. A second failure ends the wait as unknown, never green.
- A session waits on CI through the CI-wake notice that follows `gh pr ready`. A push starts no notice. The guard's remedy never names `bin/merge`, because it merges when the wait ends.

Why: one `gh run watch` made 131 API calls in 60 s, about 7,900 an hour. The core limit is 5,000 an hour, shared by every session on the account. Merges failed on it.

## Holes, named

- The secondary limit is separate: a per-minute cap on REST calls that several sessions' watchers can pass together. That watchers cause it is unmeasured. The merge tool waits 60, 300 and 900 s on a rate limit (`merge-net-retry`, what bin/merge does on a network error or a rate limit).
- `ci_wake.wait_for` lists the head's runs again, at most once per 30 s, until a run that ran is judged. A skipped draft run counts as no run. A real run that starts after a judged one is never judged. Debt `ci-wake-lists-runs-once` (a later run is not judged).
- A head whose only runs are skipped wakes the session with "unknown: no run yet" at the deadline, about 55 min after `gh pr ready`. Same debt.
- A background `gh pr checks --watch` is still allowed, because the ruling names only `gh run watch`. Debt `pr-checks-watch-unmeasured` (the background checks watch is unmeasured).
- The guard does not read a watch wrapped in `bash -c`, `cmd /c` or `pwsh -Command`, or a captured one such as `x=$(gh run watch 7)`. Guards stop Claude's mistakes, not an attacker (`guard-guards-mistakes-only`). Same debt.
- A merge wait reads the checks and runs every 30 s, about 6 calls a minute. Unmeasured on a real run.

Kind: build
Plan: decisions/ci-wait-reads-run-status.md#the-ruling (all)
