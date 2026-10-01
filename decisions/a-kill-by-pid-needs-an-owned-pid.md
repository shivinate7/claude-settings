# A kill by pid needs a pid this session started

CLAUDE.md says: "Never kill a process you did not start." The guard denied a kill by
name or by pattern. It passed `kill <pid>` for any pid, so a guessed pid, or a pid read
from another agent's server, went through.

## How the guard knows a pid is owned

Measured on macOS: every Bash command and every hook of one session descends from one
process whose command path ends in `claude`. The hook finds that process by walking its
own parent chain. A pid is owned when its own parent chain reaches that process, or when
the process is already dead (`ps` exits 1 with no output). Any other `ps` failure is unknown.
The `claude` process itself is not owned. Another session's process, and the owner's editor, do not
descend from it.

`ps -o ppid=` and `ps -o comm=` give the reads. No pid list is kept, so nothing can rot.

## The rule

`kill` with a literal pid is denied under rule `machine-wide-kill` when the pid is not owned.
Pids 0, 1, and -1 are always denied, also when the session root is unknown.
`kill $(pgrep ...)`, `kill $(pidof ...)`, and `pgrep ... | xargs kill` name a target by
pattern. They are denied as a kill by name, the same as `pkill`. A pid group (`-123`) is judged by its leader.

## What it does not cover

- `$!`, `$PID`, `%1`, `$(...)`: the guard cannot read them, so they pass. The remedy asks
  for `$!`.
- A process that reparented to init reads as foreign. Stop it through the harness.
- When no `claude` ancestor or no `ps` exists (Windows, unmeasured), the guard allows.
  Unknown is not a verdict. `taskkill /PID` and `Stop-Process -Id` pass for the same reason.

## Test hook

`CLAUDE_GUARD_ROOT_PID` (ASCII digits only) replaces the walk. The test suite sets it. A command
cannot set it, because the harness sets the hook's environment. A settings.json `env` block can.

## Outcome protected

An agent cannot stop another agent's server or the owner's editor by pid. Guard: the
`kill:` cases in `hooks/test_guard.py`, mutations in `hooks/mutate_guard.py`.
