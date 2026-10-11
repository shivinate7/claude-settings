# A stalled background command is reported, never stopped

## The question

A background command can stop making progress. How does the session learn of it, and what
happens to the command?

## The ruling (owner, 2026-10-10)

The session must learn within minutes and diagnose the cause. When the stall is reported, the
stuck command keeps running.

## How it works

`hooks/stall_watch.py` has two modes.

- Hook (`--hook`, a PreToolUse hook on Bash): for a call with `run_in_background` true, it
  returns `updatedInput` only. It sets no permission decision, so no permission changes.
- The rewritten command runs in the harness shell, not in `bash -c`. The original command stays
  as unquoted top-level shell code inside `{ ... }`. A settings deny rule still sees it, and
  the shell parses it as it would without the hook. Output goes to a log file in the system
  temp directory. The shell starts the watcher with the job's pid.
- Watcher (`--watch-pid`): it streams the log to stdout. Any new byte, also a bare `\r`
  progress byte, resets the timer. After 300 quiet seconds, it prints a STALL report and exits
  3. The job keeps running, and its output keeps going to the log. If the job ends first, the
  watcher exits 0, the shell returns the job's code, and the shell removes the log.

The report holds these items:

- the pid
- the job and its descendants, with state and elapsed time
- the open files whose path contains "lock", and the network connections (both from `lsof`,
  when it is installed)
- the last 20 output lines
- the log path

Each `ps` and `lsof` call has a 5-second limit, so the report cannot hang.

The report tells the session to ask the owner to stop the job. After the report, the job is
not a child of the session, and the guard denies a stop of a process outside the session.

`STALL_WATCH_QUIET` overrides the 300 seconds. Use it for tests and proofs only.

## The incident

In feed-build, a `playwright install` ran 73 minutes unnoticed. A stale cache lock held it. The
session had no signal that the command was idle. The report names the lock file, so the cause is
visible at once.

## Rejected

- Stop the command on a timer. A slow but healthy job would die, and the stop loses the state
  that explains the stall.
- A polling timer in the session. Rule verification-never-waiter-loop forbids a waiter loop.
  The watcher does the waiting, and the session is told once.
- Run the original in `bash -c` with quoting. The deny rules then see one quoted string, and
  the shell differs from the one the session expects.

## Known limits

- Windows is not covered. The hook returns nothing when `os.name` is not posix.
- A job that is quiet but healthy is reported, not stopped. The session decides.
- A command that prints progress forever is never reported, even when it is stuck.
- After a stall report, the log stays in the temp directory. Nothing removes it.
- A command that backgrounds its own child is not watched. The guard denies that shape anyway.
- Allow rules still match a rewritten command. Measured: with only `Bash(echo:*)` allowed, the
  rewritten echo ran. The hook does not widen or narrow what the allow list permits.
- The watcher checks the job with `ps` once each second.
