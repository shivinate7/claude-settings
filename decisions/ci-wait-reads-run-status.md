# CI waits read the run status

## The ruling

Owner, 2026-10-16 01:47 CDT ("Status read only") and 03:00 CDT ("Change them too"): no program and no agent runs `gh run watch`, in the foreground or the background. Each wait reads the run's status until the run ends or its deadline passes. `bin/merge` reads once every 30 s. The CI wake reads 30 s apart for the first 4 minutes, then at gaps that grow to 120 s (owner, 2026-10-21, back-off).

- `merge/merge.py`, `block`: no watch. It pauses 30 s. The next pass of the wait loop reads the checks and runs.
- `hooks/ci_wake.py`, `watch_run`: no watch. It reads `gh run view <id> --json status` on one schedule (`pauses`): 30 s apart through 240 s, then gaps that grow by 30 s up to 120 s, never shorter than the gap before. `wait_for` lists the head's runs on the same schedule. The watch returns when the status is `completed` or the deadline passes. The deadline stays 3300 s, and `watch_run` makes no status read at or after it. A failed read gets one retry after a 30 s pause, never past the deadline. A second failure ends the wait as unknown, never green.
- A session waits on CI through the CI-wake notice that follows `gh pr ready`. The guard's remedy never names `bin/merge`, because it merges when the wait ends.

Why: one `gh run watch` made 131 API calls in 60 s, about 7,900 an hour. The core limit is 5,000 an hour, shared by every session on the account. Merges failed on it.

### The CI wake-up

Owner, 2026-10-13 11:20 CDT: the CI wake-up hook lives in claude-settings. The mods session drops its own CI wake-up step. The hook is a Python hook registered in `settings.json`, with a red test first.

A PostToolUse hook on Bash and PowerShell (`hooks/ci_wake.py`) starts an `asyncRewake` watcher after `gh pr ready <n>`.

- Each `gh pr ready` in one command gets its own watch. A push alone starts no watch, because a PR goes ready after its last push and a push read can see the old head. A draft PR starts no watch. The hook's `settings.json` row reads `tool_input` only. It starts python only when gh, pr and ready occur in that order, each at most 16 characters after the one before (any case of gh).
- The watcher reads the PR head once and waits on its runs. A head whose only runs are skipped counts as no run yet.
- It exits 2 with a one-line verdict, which wakes the session even when idle. It stops at its own deadline, under the hook `timeout`, and wakes with "still running".
- One watcher runs per PR: a second one for the same PR exits at once.
- Text in quotes, in a heredoc body or after `#` never starts a watch. Any error, including an import or flush error, wakes with an "unknown" line.

Why: sessions waited for CI with long background commands that ran on for hours.

### The cloud wake

A cloud session has no `gh` and no PostToolUse hook, so it waits through the PR subscription. A watched PR wakes its session on a new comment, a review, and a run whose jobs all passed. A run with a red job sends no "all checks done" wake, and a green job alone wakes nobody. Batch 649's macOS job went red while its other jobs ran on. The build advisor set no check-in, so no session moved for about 2.5 hours (owner gripe, 2026-10-26, step c88).

- `gates.yml`'s last job, `ci-done`, needs every other job and runs when no run was cancelled. When a job ended `failure` or `cancelled`, it posts one PR comment: the head, each red job and the run link. A green run posts nothing. A superseded run posts nothing. `actions/ci-done-comment` holds the script, and other repos call it.
- Unmeasured: that a comment by `github-actions[bot]` wakes a subscribed session. The first red batch run after this lands measures it.
- The fallback: a session that waits on CI sets a `send_later` check-in when it starts to wait, and again after each red job, each wider apart (rule `git-ci-wait-checks-in`). A check-in costs one read, and it catches a lost wake.

Kind: build
Plan: decisions/ci-wait-reads-run-status.md#the-ruling (all)
