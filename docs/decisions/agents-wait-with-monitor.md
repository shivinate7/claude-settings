# Agents wait with the Monitor tool

## The ruling

Owner, 2026-10-11 and 2026-10-12: the `Monitor` tool, Claude Code's own wait-once tool, is allowed. `settings.json` does not list it under `permissions.deny`. The `waiter` rule in `hooks/guard_stream.py` (`waiter_verdict`) refuses only real waste:

- a loop that pauses, in bash or PowerShell;
- two or more pauses in one command, the sleep-then-poll form;
- one pause of 25 s or more. The 25 s is the figure read from the Claude CLI's leading-sleep block in claude.exe 2.1.295 (origin commit `ca4f96d2e`). Unmeasured: whether the current CLI still holds 25 (2.1.325 shows no `tengu_amber_sentinel` string). The guard differs from the CLI: the CLI refuses a leading sleep only, and the guard refuses a pause of 25 s or more in any position (`echo start; sleep 30` is refused). The mistake it guards: Claude sleeps 25 s or more to wait for a build or a CI run, which Monitor or the completion notice waits for without a turn spent;
- `gh pr checks --watch` in the foreground;
- `gh run watch` in the foreground or the background (`ci-wait-reads-run-status`, CI waits read the run status);
- `timeout /t`, which the ruling did not name.

It allows one `sleep` or `Start-Sleep` under 25 s anywhere in a command, and a background `gh pr checks --watch`. A word inside a quoted string or a heredoc body is not a call. The remedy names the CI-wake notice that follows `gh pr ready`, or Monitor.

Why: the guard once refused Monitor and all short pauses, so an agent that followed the Bash tool's text lost a turn. Almost none of the refusals were real loops. That count is unmeasured: it has no source or re-run command.
Whether Monitor still errors is unmeasured too (notes entry `waiter-monitor-failures-unmeasured`).

Monitor waits for a condition, such as a port or a file. A long command still runs in the background, and the agent waits for its completion notice.

Kind: process
Home: hooks/guard_stream.py
