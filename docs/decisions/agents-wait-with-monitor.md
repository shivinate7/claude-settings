# Agents wait with the Monitor tool

## The ruling

Owner, 2026-10-11 and 2026-10-12: the `Monitor` tool, Claude Code's own wait-once tool, is allowed. `settings.json` does not list it under `permissions.deny`. The `waiter` rule in `hooks/guard_stream.py` (`waiter_verdict`) refuses only real waste:

- a loop that pauses, in bash or PowerShell;
- two or more pauses in one command, the sleep-then-poll form;
- one pause of 25 s or more;
- `gh pr checks --watch` in the foreground;
- `gh run watch` in the foreground or the background (`ci-wait-reads-run-status`, CI waits read the run status);
- `timeout /t`, which the ruling did not name.

It allows one `sleep` or `Start-Sleep` under 25 s anywhere in a command, and a background `gh pr checks --watch`. A word inside a quoted string or a heredoc body is not a call. The remedy names the CI-wake notice that follows `gh pr ready`, or Monitor.

Why: the guard once denied Monitor and all short pauses, so an agent that followed the Bash tool's text lost a turn. Almost none of the refusals were real loops.

Monitor waits for a condition, such as a port or a file. A long command still runs in the background, and the agent waits for its completion notice.

Kind: process
Home: hooks/guard_stream.py
