# CI waits read the run status

## The ruling

Owner, 2026-10-16 01:47 CDT ("Status read only") and 03:00 CDT ("Change them too"): no program and no agent runs `gh run watch`, in the foreground or the background. Each wait reads the run's status at most once every 30 s, until the run ends or its deadline passes.

- `merge/merge.py`, `block`: no watch. It pauses 30 s. The next pass of the wait loop reads the checks and runs.
- `hooks/ci_wake.py`, `watch_run`: no watch. It reads `gh run view <id> --json status` once every 30 s, and returns when the status is `completed` or the deadline passes. A failed read gets one retry after the 30 s pause, never past the deadline. A second failure ends the wait as unknown, never green.
- A session waits on CI through the CI-wake notice that follows `gh pr ready`. A push starts no notice. The guard's remedy never names `bin/merge`, because it merges when the wait ends.

Why: one `gh run watch` made 131 API calls in 60 s, about 7,900 an hour. The core limit is 5,000 an hour, shared by every session on the account. Merges failed on it.

Kind: build
Plan: decisions/ci-wait-reads-run-status.md#the-ruling (all)
