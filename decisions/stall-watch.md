# A stalled background command is reported, never stopped

## The ruling

The session learns within minutes that a background command stalled, and diagnoses the cause. When the
stall is reported, the stuck command keeps running. Reason: a `playwright install` ran 73 minutes
unnoticed behind a stale cache lock, and the report names the lock file.

`hooks/stall_watch.py` has two modes.

- Hook (`--hook`, a PreToolUse hook on Bash): for a call with `run_in_background` true, it returns
  `updatedInput` only. It sets no permission decision, so no permission changes.
- The rewritten command runs in the harness shell, not in `bash -c`. The original command stays as
  unquoted top-level shell code inside `{ ... }`. A settings deny rule still sees it, and the shell
  parses it as it would without the hook. Output goes to a log file in the system temp directory. The
  shell starts the watcher with the job's pid.
- Watcher (`--watch-pid`): it streams the log to stdout. Any new byte, also a bare `\r` progress byte,
  resets the timer. After 300 quiet seconds, it prints a STALL report and exits 3. The job keeps running,
  and its output keeps going to the log. If the job ends first, the watcher exits 0, the shell returns
  the job's code, and the shell removes the log.

The report holds these items:

- the pid
- the job and its descendants, with state and elapsed time
- the open files whose path contains "lock", and the network connections (both from `lsof`, when it is installed)
- the last 20 output lines
- the log path

Each `ps` and `lsof` call has a 5-second limit, so the report cannot hang. The report tells the session
to ask the owner to stop the job. After the report, the job is not a child of the session, and the guard
denies a stop of a process outside the session. `STALL_WATCH_QUIET` overrides the 300 seconds, for tests
and proofs only.

Rejected:

- Stop the command on a timer. A slow but healthy job would die, and the stop loses the state that explains the stall.
- A polling timer in the session. The `waiter` guard rule refuses a waiter loop. The watcher does the waiting, and the session is told once.
- Run the original in `bash -c` with quoting. The deny rules then see one quoted string, and the shell differs from the one the session expects.

**Tools that are quiet by design.** A tool that waits with no output must print a short progress line at
least every 120 seconds. The watcher does not change. A false STALL teaches the reader to scroll past a
real one (guard-that-cries-wolf-is-spent).

- The merge tool prints `merge: waiting on ...` while it waits on checks, and while GitHub still shows the head before the push.
- `verdict` prints `verdict: still running, <elapsed>, log=<path>` every 120 seconds. `VERDICT_HEARTBEAT` sets another whole number of seconds, for tests.

Kind: process
Home: hooks/stall_watch.py

## Known limits

- Windows is not covered. The hook returns nothing when `os.name` is not posix. The Stop-time check (`stall-watch-stop-check`) reports a background shell left open at turn end.
- A job that is quiet but healthy is reported, not stopped. The session decides.
- A command that prints progress forever is never reported, even when it is stuck.
- After a stall report, the log stays in the temp directory. Nothing removes it.
- A command that backgrounds its own child is not watched. The guard denies that shape anyway.
- Allow rules still match a rewritten command. The hook does not widen or narrow what the allow list permits.
- Under zsh, a trailing `\` continuation leaves one empty word. sh and bash drop it. The exit code differs only when a lone `\` line follows a failing command: bare zsh gives 126, and the rewrite keeps the failing code.
- A command ending in an odd run of `\` behaves by shell: dash and bash 5 keep the last one as a literal at end of input, bash 3.2 drops it. The hook probes `/bin/sh` and, when it keeps the literal, doubles the last `\` so the rewrite matches bare. Measured on dash, not on Linux CI. The probe reads `/bin/sh`, not the user's shell, so a zsh user on a host whose `/bin/sh` is dash gets an extra `\` on that last word.
- The watcher checks the job with `ps` once each second.
