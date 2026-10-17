# Agents wait with the Monitor tool

## The ruling

Owner, 2026-10-11 and 2026-10-12: the `Monitor` tool, Claude Code's own wait-once tool, is allowed. `settings.json` does not list it under `permissions.deny`. The `waiter` rule in `hooks/guard.py` (`waiter_verdict`) refuses only real waste:

- a loop that pauses, in bash or PowerShell;
- two or more pauses in one command, the sleep-then-poll form;
- one pause of 25 s or more;
- `gh pr checks --watch` in the foreground;
- `gh run watch` in the foreground or the background (`ci-wait-reads-run-status`, CI waits read the run status);
- `timeout /t`, which the ruling did not name.

It allows one `sleep` or `Start-Sleep` under 25 s anywhere in a command, and a background `gh pr checks --watch`. A word inside a quoted string or a heredoc body is not a call. The remedy names the CI-wake notice that follows `gh pr ready`, or Monitor.

Why: Claude Code's own check refuses only a leading `sleep` of 25 s or more. The guard denied Monitor and all short pauses, so an agent that followed the Bash tool's text, or reached for `sleep`, lost a turn. Almost none of the refusals were real loops.

Monitor waits for a condition, such as a port or a file. A long command still runs in the background, and the agent waits for its completion notice.

## Limits

- Unmeasured: whether Monitor still errors. The weekly table (`guard-log-read-weekly`) carries the `waiter` count. Reopen on a measured count of Monitor failures in agent reports, or a `waiter` count that does not fall.
- Watcher detection matches `gh run watch`, and `gh pr checks` with `--watch` or `--watch=...`. `gh` and `gh.exe` both count.
- `bash -c '...'` and subshell bodies, such as `(sleep 30)` and `$(sleep 30)`, are not parsed (accepted by the owner).
- `sleep 20 20` reads as 20 s, not 40 s, and passes.
- The loop flag spans the whole command, so a pause after any unrelated loop is refused. A loop with no loop word, such as `(1..10).ForEach({ Start-Sleep 1 })`, is not seen.
- `echo {sleep}`, `--watch=false` and `gh pr checks 5 -R --watch` are refused, all false alarms.
- No test pins `--repo o/r`, `--repo=o/r`, `-Ro/r` or the `gh run -R watch list` false-alarm guard.
- An agent may still burn up to 25 s per call on a single pause.

Kind: process
Home: hooks/guard_stream.py
