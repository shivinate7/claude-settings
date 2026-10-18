# A stalled background command is reported, never stopped

## The ruling

The session learns within minutes that a background command stalled, and diagnoses the cause. When the
stall is reported, the stuck command keeps running. Reason: a `playwright install` hung unnoticed behind a
stale cache lock, and the report names the lock file. A stop on a timer would kill a slow but healthy job
and lose the state that explains the stall. A polling timer in the session is refused by the `waiter`
guard rule, so the watcher does the waiting and the session is told once.

`hooks/stall_watch.py` has two modes.

- Hook (`--hook`, a PreToolUse hook on Bash): for a call with `run_in_background` true, it returns
  `updatedInput` only. It sets no permission decision, so no permission changes.
- The rewritten command runs in the harness shell, not in `bash -c`. The original command stays as
  unquoted top-level shell code inside `{ ... }`, so a settings deny rule still sees it. Output goes to a
  log file in the system temp directory. The shell starts the watcher with the job's pid. Allow rules still
  match a rewritten command.
- Watcher (`--watch-pid`): it streams the log to stdout. Any new byte resets the timer. After 300 quiet
  seconds, it prints a STALL report and exits 3. The job keeps running, and its output keeps going to the
  log. If the job ends first, the watcher exits 0, the shell returns the job's code, and the shell removes
  the log. `STALL_WATCH_QUIET` overrides the 300 seconds, for tests and proofs only.
- The report holds the pid, the job and its descendants (state, elapsed time), the open files whose path
  contains "lock", the network connections, the last 20 output lines, and the log path. Files and
  connections come from `lsof`, when installed. Each `ps` and `lsof` call has a 5-second limit.
- The report tells the session to ask the owner to stop the job. After the report, the job is not a child
  of the session, and the guard denies a stop of a process outside the session.
- A tool that is quiet by design must print a short progress line at least every 120 seconds. The watcher
  does not change, because a false STALL teaches the reader to scroll past a real one
  (guard-that-cries-wolf-is-spent). The merge tool prints `merge: waiting on ...` while it waits on checks,
  and while GitHub still shows the head before the push. `verdict` prints `verdict: still running,
  <elapsed>, log=<path>` every 120 seconds (`VERDICT_HEARTBEAT` sets another whole number, for tests).

Limits:

- Windows is not covered: the hook returns nothing when `os.name` is not posix. The Stop-time check
  (`stall-watch-stop-check`) reports a background shell left open at turn end.
- A quiet but healthy job is reported, not stopped. The session decides.
- A command that prints progress forever is never reported, even when stuck.
- After a stall report, the log stays in the temp directory. Nothing removes it.
- A command that backgrounds its own child is not watched. The guard denies that shape anyway.
- A trailing `\` continuation and an odd run of `\` at the end of a command behave by shell. The hook
  probes `/bin/sh` and, when it keeps the last `\` as a literal, doubles it, so the rewrite matches the
  bare command.

Kind: process
Home: hooks/stall_watch.py
