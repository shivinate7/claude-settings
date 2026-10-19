# CI waits read the run status

## The ruling

Owner, 2026-10-16 01:47 CDT ("Status read only") and 03:00 CDT ("Change them too"): no program and no agent runs `gh run watch`, in the foreground or the background. Each wait reads the run's status at most once every 30 s, until the run ends or its deadline passes.

- `merge/merge.py`, `block`: no watch. It pauses 30 s. The next pass of the wait loop reads the checks and runs.
- `hooks/ci_wake.py`, `watch_run`: no watch. It reads `gh run view <id> --json status` once every 30 s, and returns when the status is `completed` or the deadline passes. A failed read gets one retry after the 30 s pause, never past the deadline. A second failure ends the wait as unknown, never green.
- A session waits on CI through the CI-wake notice that follows `gh pr ready`. The guard's remedy never names `bin/merge`, because it merges when the wait ends.

Why: one `gh run watch` made 131 API calls in 60 s, about 7,900 an hour. The core limit is 5,000 an hour, shared by every session on the account. Merges failed on it.

### The CI wake-up

Owner, 2026-10-13 11:20 CDT: the CI wake-up hook lives in claude-settings. The mods session drops its own CI wake-up step. The hook is a Python hook registered in `settings.json`, with a red test first.

A PostToolUse hook on Bash and PowerShell (`hooks/ci_wake.py`) starts an `asyncRewake` watcher after `gh pr ready <n>`.

- Each `gh pr ready` in one command gets its own watch. A push alone starts no watch, because a PR goes ready after its last push and a push read can see the old head. A draft PR starts no watch. The hook exits before imports when the command has no `ready`.
- The watcher reads the PR head once and waits on its runs. A head whose only runs are skipped counts as no run yet.
- It exits 2 with a one-line verdict, which wakes the session even when idle. It stops at its own deadline, under the hook `timeout`, and wakes with "still running".
- One watcher runs per PR: a second one for the same PR exits at once.
- Text in quotes, in a heredoc body or after `#` never starts a watch. Any error, including an import or flush error, wakes with an "unknown" line.

Why: sessions waited for CI with long background commands that ran on for hours.

Kind: build
Plan: decisions/ci-wait-reads-run-status.md#the-ruling (all)
