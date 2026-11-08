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

Why: the guard once refused Monitor and all short pauses, so an agent that followed the Bash tool's text lost a turn. Almost none of the refusals were real loops. That count is unmeasured: it has no source or re-run command.
Whether Monitor still errors is unmeasured too (notes entry `waiter-monitor-failures-unmeasured`).

Monitor's `command` goes through the shell guard (`judge_shell`, `hooks/guard.py`) like a Bash command, except the stream family: live-stream, waiter, narrated tail and background-end never refuse a Monitor call. Every other rule applies, so a raw `xcrun simctl boot` or `git reset --hard` is refused inside a Monitor (`sim-test-is-the-one-boot-path`). `settings.json` lists Monitor in the first guard matcher.
Basis: owner, coordinator pick (b), 2026-11-08 11:23 CST, under item 386.
Cost: one guard run per Monitor call. No new process, no file written on an allowed call.

Monitor waits for a condition, such as a port or a file. A long command still runs in the background, and the agent waits for its completion notice.

Kind: process
Home: hooks/guard_stream.py
