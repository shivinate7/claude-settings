# A stalled background command is reported, never killed

## The question

A background command can stop making progress. How does the session learn of it, and what
happens to the command?

## The ruling (owner, 2026-10-10)

The session must learn within minutes and diagnose the cause. When the stall is reported, the
stuck command keeps running.

## How it works

`hooks/stall_watch.py` has two modes.

- Hook (`--hook`, a PreToolUse hook on Bash): for a call with `run_in_background` true, it
  rewrites the command to run the wrapper around the original. Other calls pass unchanged.
- Wrapper: it runs the command in its own process group, with its output going to a log file.
  It passes that output to its own stdout. If no new output comes for 300 seconds, it prints a
  STALL report and exits 3. The exit tells the session that the task ended. The command keeps
  running, and its output keeps going to the log. If the command ends first, the wrapper exits
  with the command's code.

The report holds these items:

- the pid and the pgid
- each process in the group, with state and elapsed time
- the open files whose path contains "lock", and the network connections (both from `lsof`,
  when it is installed)
- the last 20 output lines
- the log path

`STALL_WATCH_QUIET` overrides the 300 seconds. Use it for tests and proofs only.

## The incident

In feed-build, a `playwright install` ran 73 minutes unnoticed. A stale cache lock held it. The
session had no signal that the command was idle. The report names the lock file, so the cause is
visible at once.

## Rejected

- Kill the command on a timer. A slow but healthy job would die, and a kill loses the state
  that explains the stall.
- A polling timer in the session. Rule verification-never-waiter-loop forbids a waiter loop.
  The wrapper does the waiting, and the session is told once.

## Known limits

- Windows is not covered. The wrapper needs `ps`, process groups, and `bash`.
- A job that is quiet but healthy is reported, not stopped. The session decides.
- Quiet is the lack of output. A command that prints dots forever is never reported.
- The wrapper reads the log by polling it every 0.2 seconds. This costs little CPU.
- A command that closes its output and detaches fully is not followed after the wrapper ends.
