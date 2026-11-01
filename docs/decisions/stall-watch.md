# A stalled background command is reported, never stopped

## The ruling

The session learns within minutes that a background command stalled, and diagnoses the cause. The Stop-time check lists stalled shells and never refuses.
When the stall is reported, the stuck command keeps running. Reason: a `playwright install` hung unnoticed behind a
stale cache lock, and the report names the lock file. A stop on a timer would kill a slow but healthy job
and lose the state that explains the stall. A polling timer in the session is refused by the `waiter`
guard rule, so the watcher does the waiting and the session is told once.

`hooks/stall_watch.py` does it.

- The hook (`--hook`, a PreToolUse hook on Bash) returns `updatedInput` only for a call with
  `run_in_background` true. It sets no permission decision, so no permission changes.
- The original command stays as unquoted top-level shell code inside `{ ... }`, so a settings deny rule
  still sees it. Allow rules still match a rewritten command.
- The STALL line lists the job's shell and every process under it, parent first, so stopping them in line
  order ends the job (owner ruling, 2026-10-18). The shell gives the watcher the pid of `&`; in sh,
  bash and zsh a `{ }` group runs in a forked copy of the shell. The report reads the process table only
  and never scans the command text. A parent dies before it can start another child. A job with no child
  (builtins only) lists its own pid. The table lists the same processes. Two limits: an orphan (`(sleep N &); sleep N`) is adopted by
  init and not listed, and a TERM trap that returns respawns a loop body (SIGKILL ends it).
- The watcher (`--watch-pid`) prints a STALL report and exits 3 after 300 quiet seconds. The job keeps
  running and the watcher never stops it. The wrapper keeps exit 3 after a stall, so the session gets no
  exit code from the job, even a healthy silent one such as `python3 hooks/test_guard.py` (owner ruling,
  2026-10-18 15:15 CDT).
- The report tells the session to ask the owner to stop the job. After the report, the job is not a child
  of the session. The guard refuses a stop of a process outside the session, unless the owner's override
  covers it (`owner-override`, the owner's typed override).
- The one allowed wait on a stranded job is `wait-pid <pid> [--timeout SECS]` (`bin/wait-pid`). Incident,
  2026-10-31: a stall left a lane with its job's pid, and the guards refused a `kill -0` loop, a `/proc`
  poll and `tail --pid`. Those loops stay refused; the remedies of the `waiter` and `live-stream` rules
  and the STALL report name the helper. It waits only on a pid that `guard_kill.pid_is_session_job`
  calls this session's, and exits 2 at once for any other pid. A pid is this session's in three cases. It
  descends from the session root. Or its walk reaches init with this session's tag on the pid or an
  ancestor below init. Or it has PPID 1 and a descendant holds the tag. The last covers the STALL report's first pid, the
  untagged stub. It also owns a foreign PPID-1 process with a descendant this session started; the harm
  is a wait, never a signal. Unmeasured: a stub adopted by a subreaper (PPID above 1, such as
  `systemd --user`) reads foreign, so the helper exits 2 on it. The descendant scan skips the helper's own chain and stops at depth 8 or 512 pids. Exit
  0 when the pid ends, 124 at the timeout (default 540 s), 3 when a liveness read fails (unknown, never
  read as ended). A foreground Bash call stops at 120 s by default, so the STALL report says to run a long
  wait with `run_in_background`. It prints a `still waiting` line every 120 s, so a background wait draws
  no STALL. It cannot read the job's exit code: the job is not its child. Start-time check against pid
  reuse. Not on Windows. Cost: one process per wait, no file written. At start, the ownership walk runs up to
  three short `ps` reads per ancestor level and at most one process-table read (unmeasured count). While it waits, four `/proc` reads a second
  on Linux, one `ps` a second elsewhere. Unmeasured: no test pins the cost.
- A tool that is quiet by design must print a short progress line at least every 120 seconds. The merge
  tool prints `merge: waiting on ...` while it waits on checks, and while GitHub still shows the head before
  the push. `verdict` prints a `still running` line to stderr every 120 seconds, so a pipe on stdout does not hide it.
- A job that sends that line to a log it names is still writing, so it is no stall (owner ruling,
  2026-10-26: the watcher reads named logs, in place of the rule that it does not change). Reason:
  `merge.py ... > LOG 2>&1` was reported stalled while it worked, and a false STALL teaches the reader to
  scroll past a real one (guard-that-cries-wolf-is-spent). The hook reads the logs from the command itself
  (`named_logs`): the target of `> F`, `>> F`, `&> F`, `>& F`, each `tee` file, and `--log F`. shlex reads
  the command, so a path in quotes or a comment is text. A change of size or mtime on any of them resets the
  quiet time. A job with no named log, or whose logs stop changing, stalls as before. The redirection is the
  signal because it is the act; a declared note can be wrong, and an unnamed file is not read. Limit: a
  relative path after a `cd` resolves against the shell's directory, so that job can still stall falsely.
  The watcher reports a stall only on a job state and named-log sample from the same pass. A sample
  from the once-a-second check can be a second old, and miss a write or the job's end.
  Cost: no new process, timer or file. Each named log gets one stat a second in the watcher's own loop,
  one more before each stall report, and one at each Stop check.

## The Stop-time check

When a turn ends, a Stop hook runs `hooks/stall_watch.py --stop`. It reads the session transcript and
lists each open background shell whose output file has been quiet longer than the age. Each log its
command names must be quiet too. A relative log resolves against the call record's `cwd`. A shell whose
output file is not found is listed as unknown. It prints one systemMessage that tells the model to stop
the shell or tell the owner.

The hook exits 0 and never refuses. A crash never refuses a call, as advisory hooks stay fail-open
(`guard-hooks-fail-closed`). It reuses the transcript parsing of the PreToolUse path, so that parsing has
one home (`building-one-home-per-capability`).

- Age: the default is 300 seconds, a builder's choice, not measured. `STALL_WATCH_QUIET` sets another
  number of seconds.
- A job counts as finished when the transcript holds a completion notice with status completed, failed,
  killed or stopped (as a user record, or as an attachment record of type queued_command), or a
  "Successfully stopped task: <ID>" result of a TaskStop call.

Reason: the PreToolUse path runs only at a tool call, and on Windows it does nothing. No process id
exists for the job, so the age of its output file is the signal.

Kind: process
Home: hooks/stall_watch.py
