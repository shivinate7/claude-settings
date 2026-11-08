# Agents wait with the Monitor tool

## The ruling

Owner, 2026-10-11 and 2026-10-12: the `Monitor` tool, Claude Code's own wait-once tool, is allowed. `settings.json` does not list it under `permissions.deny`. The `waiter` rule in `hooks/guard_stream.py` (`waiter_verdict`) refuses only real waste:

- a loop that pauses, in bash or PowerShell;
- two or more pauses in one command, the sleep-then-poll form;
- one pause of 25 s or more;
- `gh pr checks --watch` in the foreground;
- `gh run watch` in the foreground or the background (`ci-wait-reads-run-status`, CI waits read the run status);
- `timeout /t`, which the ruling did not name.

It allows one `sleep` or `Start-Sleep` under 25 s anywhere in a command, and a background `gh pr checks --watch`. A word inside a quoted string or a heredoc body is not a call. In a quoted python, node or perl heredoc body, a `\'` escape keeps the string open (guard_core `_interpreter_text_spans`); its limit is the note `guard-heredoc-os-system`, which says the guard does not read those bodies. The remedy names the CI-wake notice that follows `gh pr ready`, or Monitor.

The guard sees a Monitor call as a Bash call. Monitor's input carries `timeout_ms`, and Bash's carries `timeout`. The guard tells Monitor by `timeout_ms` with no `timeout`, and no `run_in_background`. It then allows poll loops and pauses of any length. `gh pr checks --watch`, `gh run watch` and `timeout /t` stay refused under Monitor. A watcher polls the API on its own clock (`gh run watch` made 131 calls in 60 s, decision `ci-wait-reads-run-status`), and a CI wait has its own home, the CI-wake notice. Monitor adds no wait the notice lacks. The refusal gives a Monitor-specific reason, `WAITER_MONITOR_REASON`. The guard trusts `timeout_ms` because the Bash schema allows no such key. A Bash call with `timeout` is judged as a foreground call.

Cost: no new process and no new file. The guard reads one more key of the call it already judges.

Why: the guard once refused Monitor and all short pauses, so an agent that followed the Bash tool's text lost a turn. Almost none of the refusals were real loops. That count is unmeasured: it has no source or re-run command.
Whether Monitor still errors is unmeasured too (notes entry `waiter-monitor-failures-unmeasured`).

Monitor waits for a condition, such as a port or a file. A long command still runs in the background, and the agent waits for its completion notice.

Kind: process
Home: hooks/guard_stream.py
