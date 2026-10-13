# Agents wait with the Monitor tool

## The question

Which way may an agent wait for a condition? The guard refuses `sleep`, and the settings
denied the tool the harness points at.

## The ruling, 2026-10-11 (owner)

The `Monitor` tool, Claude Code's own wait-once tool, is allowed. `settings.json` no longer
lists it under `permissions.deny`.

Narrowed by the owner, 2026-10-12. The `waiter` rule in `hooks/guard.py` (`waiter_verdict`)
refuses only real waste:

- a loop that pauses, in bash or PowerShell;
- two or more pauses in one command, the sleep-then-poll form;
- one pause of 25 s or more;
- a CI watcher (`gh pr checks --watch`, `gh run watch`) in the foreground;
- `timeout /t`, which the ruling did not name.

It allows one `sleep` or `Start-Sleep` under 25 s anywhere in a command, and a watcher run
with `run_in_background`. A word inside a quoted string or a heredoc body is not a call. The
remedy names a background watcher run once, or Monitor.

Why: Claude Code's own check refuses only a leading `sleep` of 25 s or more (flag
`tengu_amber_sentinel`, threshold 25, read from claude.exe 2.1.295). Of 468 measured refusals,
none was that kind. About 300 were one short pause, about 130 were real loops, and 14 matched
only quoted text.

## The incident

Commit a5af6d6 (2026-09-16) denied Monitor because "it errors often", and a background command
with a completion notice "does the same job". Nothing measured it after that day.

MEASURED in this Windows machine's `~/.claude/guard.log`, 2026-09-16 to 2026-10-11: 464
`waiter` denies, every one `sleep` or `Start-Sleep`. The Bash tool's own text tells an agent to
use Monitor for a wait. An agent that followed that text was refused. An agent that reached for
`sleep` was refused. Each deny is one turn thrown away, then a retry.

## Named limits

- Whether Monitor still errors is unmeasured. The weekly table (decision guard-log-read-weekly)
  carries the `waiter` count. The first table after this change is the measurement.
- Watcher detection matches `gh run watch`, and `gh pr checks` with `--watch` or
  `--watch=...`. `gh` and `gh.exe` both count.
- `bash -c '...'` and subshell bodies, such as `(sleep 30)` and `$(sleep 30)`, are not parsed.
  The owner accepted this gap (guard.py, near the `bash -c` note).
- `sleep 20 20` reads as 20 s, not 40 s, and passes.
- The loop flag spans the whole command. A pause after any unrelated loop is refused.
- A loop with no loop word, such as `(1..10).ForEach({ Start-Sleep 1 })`, is not seen.
- `echo {sleep}` is refused: a bare word after `{` counts as a call.
- An agent may still burn up to 25 s per call on a single pause.
- Monitor waits for a condition, such as a port or a file. A long command still runs in the
  background, and the agent waits for its completion notice.

## What reopens it

A measured count of Monitor failures in agent reports, or a `waiter` deny count that does not
fall after this change.
