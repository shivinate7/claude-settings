# A kill by pid needs a pid this session started

CLAUDE.md says: "Never kill a process you did not start." The guard denied a kill by
name or by pattern. It passed `kill <pid>` for any pid, so a guessed pid, or a pid read
from another agent's server, went through.

## How the guard knows a pid is owned

Measured on macOS: every Bash command and every hook of one session descends from one
process whose command path ends in `claude`. The hook finds that process by walking its
own parent chain. A pid is owned when its own parent chain reaches that process, or when
the process is already dead. Another session's process, and the owner's editor, do not
descend from it.

`ps -o ppid=` and `ps -o comm=` give the reads. No pid list is kept, so nothing can rot.

## The rule

`kill` with a literal pid is denied under rule `machine-wide-kill` when the pid is not owned.
Pids 0, 1, and -1 are always denied. A pid group (`-123`) is judged by its leader.

## What it does not cover

- `$!`, `$PID`, `%1`, `$(...)`: the guard cannot read them, so they pass. The remedy asks
  for `$!`.
- A process that reparented to init reads as foreign. Stop it through the harness.
- When no `claude` ancestor or no `ps` exists (Windows, unmeasured), the guard allows.
  Unknown is not a verdict. `taskkill /PID` and `Stop-Process -Id` pass for the same reason.
- `pgrep x | xargs kill` names no literal pid and passes.

## Test hook

`CLAUDE_GUARD_ROOT_PID` replaces the walk. Only the test suite sets it. The harness sets the
hook's environment, so a command cannot.

## Outcome protected

An agent cannot stop another agent's server or the owner's editor by pid. Guard: the
`kill:` cases in `hooks/test_guard.py`, mutations in `hooks/mutate_guard.py`.
