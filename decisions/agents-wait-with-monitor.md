# Agents wait with the Monitor tool

## The question

Which way may an agent wait for a condition? The guard refuses `sleep`, and the settings
denied the tool the harness points at.

## The ruling, 2026-10-11 (owner)

The `Monitor` tool, Claude Code's own wait-once tool, is allowed. `settings.json` no longer
lists it under `permissions.deny`. The `waiter` rule in `hooks/guard.py` still refuses `sleep`,
`Start-Sleep` and `timeout /t`. Its remedy names Monitor first.

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
- Monitor waits for a condition, such as a port or a file. A long command still runs in the
  background, and the agent waits for its completion notice.

## What reopens it

A measured count of Monitor failures in agent reports, or a `waiter` deny count that does not
fall after this change.
