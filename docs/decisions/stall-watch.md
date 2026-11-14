# A stalled background command is reported, never stopped

## The ruling

The session learns within minutes that a background command stalled, and diagnoses the cause. The Stop-time check lists stalled shells and never refuses.
When the stall is reported, the stuck command keeps running. Reason: a `playwright install` hung unnoticed behind a
stale cache lock, and the report names the lock file. A stop on a timer would kill a slow but healthy job
and lose the state that explains the stall. A polling timer in the session is refused by the `waiter`
guard rule, so the watcher does the waiting and the session is told once.

`hooks/stall_watch.py` does it.

- The hook (`--hook`, a PreToolUse hook on Bash) returns `updatedInput` only for a call with
  `run_in_background` true. It sets no permission decision, so no permission changes. A foreground call
  gets no output, with or without `agent_id`: Claude Code checks permission rules on a hook's rewritten
  input.
- For a background call whose payload has a valid `agent_id` (17 lowercase hex), the one addition is the
  agent marker: `export CLAUDE_AGENT_ID=<id>` and a newline ahead of the wrapper, so each process the job
  execs holds the id (decision `when-a-worktree-may-be-removed`, the marker rule).
- The original command stays as unquoted top-level shell code inside `{ ... }`, so a settings deny rule
  still sees it. Allow rules still match a rewritten command.
- The STALL line lists the job's shell and every process under it, parent first, so stopping them in line
  order ends the job (owner ruling, 2026-10-18). The shell gives the watcher the pid of `&`; in sh,
  bash and zsh a `( )` subshell runs in a forked copy of the shell. The report reads the process table only
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
  reuse. Not on Windows. Cost: one process per wait, no file written (unmeasured). At start, the ownership walk runs up to
  three short `ps` reads per ancestor level and at most one process-table read (unmeasured count). While it waits, four `/proc` reads a second
  on Linux, one `ps` a second elsewhere (unmeasured). Unmeasured: no test pins the cost.
- A tool that is quiet by design must print a short progress line at least every 120 seconds. The merge
  tool beats in every phase (`phase_beat` in `merge/merge.py`): while a run is in progress, a thread appends
  `merge: still working, Ns` to `STALL_WATCH_BEAT` every `MERGE_HEARTBEAT` seconds (default 120), so a silent
  phase of a batch build draws no STALL (batch 138, batch 139 build 4; `merge/test_merge_beat.py`). It does
  nothing when the variable is unset. Cost: at most one thread a run and at most one append every 120 s, no process, pinned by
  `test_cost_one_thread_and_one_append_per_beat`. Limit: the thread beats while the main thread waits, so a
  merge run hung in a `gh` or `git` call shows life and draws no STALL. Those calls have no timeout in a real run
  (`SH_TIMEOUT` is set only by the guard's preview reads), so nothing bounds it (note `merge-beat-masks-hung-call`;
  how often it happens is unmeasured). The merge tool's own 60 s scan line goes to stdout, the beat to
  the beat file, so a redirect of stdout hides only the first. The merge
  tool also prints `merge: waiting on ...` while it waits on checks, and while GitHub still shows the head before
  the push. `verdict` prints a `still running` line to stderr every 120 seconds, so a pipe on stdout does not hide it.
  It also appends the line to the beat file, which the hook names next to its log, exports to the job as
  `STALL_WATCH_BEAT`, and passes to the watcher as `--beat`. The watcher relays the file's new bytes to its
  own output, the harness output file. So a redirect in the command (`2>&1 | grep`, `2>/dev/null`)
  hides the line from neither the watcher nor the Stop check.
  `hooks/test_guard.py` does the same. It prints a stderr line and appends to `STALL_WATCH_BEAT` at most once
  per `GUARD_HEARTBEAT` seconds (default 60) of quiet, read at checkpoints between cases. It starts no
  thread, timer or process. `hooks/test_guard_beat.py` (`BeatCost`) pins the cost.
- A job that sends that line to a log it names is still writing, so it is no stall (owner ruling,
  2026-10-26: the watcher reads named logs, in place of the rule that it does not change). Reason:
  `merge.py ... > LOG 2>&1` was reported stalled while it worked, and a false STALL teaches the reader to
  scroll past a real one (guard-that-cries-wolf-is-spent). The hook reads the logs from the command itself
  (`named_logs`): the target of `> F`, `>> F`, `&> F`, `>& F`, each `tee` file, and `--log F`. shlex reads
  the command, so a path in quotes or a comment is text. A change of size or mtime on any of them resets the
  quiet time. A job with no named log, or whose logs stop changing, stalls as before. The redirection is the
  signal because it is the act; a declared note can be wrong, and an unnamed file is not read.
  A relative log after a `cd` or `pushd` is joined to its target when the hook builds the wrapper. The same
  tokenizer reads the cd, so a cd in quotes, a comment or a heredoc body is text. Only a cd that surely
  runs in the main shell moves the directory: the first command of a list item, or one that follows only
  cds joined by `&&`. A cd behind `||`, `&`, `|` or `then`, a cd that ends in `&`, `|` or `||` (also before a newline), or inside `{ }`, leaves it unknown.
  A list that ends in `&` runs in a background subshell, so after the `&` the directory is the list's start.
  Limit: `builtin cd`, `command cd` and `eval "cd ..."` are not read as a cd.
  Limit: a cd inside a shell heredoc body (`bash <<EOF`) is read as moving the main shell.
  The hook never refuses for this (coordinator ruling, 2026-11-08). It leaves that log out of `--also`,
  passes it as `--unwatched`, and the STALL report names it. A refusal on `cd "$REPO" && make > log`
  costs more than a missed log.
  CPU time is life too (coordinator ruling, 2026-11-08 05:02 CST): a child with no output, such as
  `cmd | tail -1`, is working while its CPU time advances. Any process under the job's shell counts;
  the shell's own time does not.
  Each process also carries the CPU time of the children it has already waited for (`reaped_seconds`:
  cutime and cstime in `/proc/PID/stat`, Linux only). `ps` shows whole seconds and only live
  processes, so a silent parent that runs short children one after another (batch 139 build 4) drew a
  false STALL until this time counted. The job shell's own time stays out, its reaped children's time is in.
  Cost: no new process, timer or file. The once-a-second `ps` that reads the job's state reads the
  process table with CPU time, and the watcher compares each process to its last reading. Each check also
  reads `/proc/PID/stat` once for the job's shell and once for each process under it, so N processes
  cost N + 1 reads a second (pinned by case 25f in `hooks/test_stall_watch.py`; one `ps` pinned by 25e).
  Where `/proc` is absent the reads give 0. A fork-polling hang (`while ! mkdir lock; do sleep 1; done`) may read as life from its ended children's reaped time; unmeasured, and no test covers it. On Linux ps gives whole seconds, so a live child under 1/SECS of a core
  (0.33% at 300 s) that has not ended may still stall. A job that `exec`s has no child to count.
  Red cases: batch 138 (a silent parent with a busy child, case 25c) and batch 139 build 4 (a serial chain, case 25d).
  Kept as a stall: a child that holds a lock and does nothing, no CPU (the `playwright install` hang, case 4).
  The watcher reports a stall only on a job state and named-log sample from the same pass. A sample
  from the once-a-second check can be a second old, and miss a write or the job's end.
  Each background job starts at most one watcher process, unmeasured. Its process cost is open: owner Cockpit item 180 holds
  it (plan `docs/plans/align-watchers.md`, unmeasured). Each named log gets at most one stat a second in the watcher's own loop,
  one more before each stall report, and one at each Stop check, not pinned. The beat file costs at most one append per
  heartbeat. The watcher reads it on each 0.2 s loop pass.
- The job removes its log and beat file when it ends, also after a STALL report (the job keeps writing
  until then, so nothing is removed at stall time), and when the original calls `exit N` (the exit code is
  kept). The wrapper creates both files and opens both before the job starts. The watcher inherits those
  handles, so a job that ends at once loses no output, and the STALL report reads its tail from the
  handle. An EXIT trap in the job does the removal. The job runs as a `( )` subshell because bash 3.2
  (macOS `/bin/sh` and `/bin/bash`) runs an EXIT trap at a subshell's normal end only there. Limits: an original that execs drops the trap, and
  so does one that sets its own EXIT trap. The exec'd command replaces the job's subshell and keeps its pid, so
  the report still lists one process. A stalled job of that kind leaves its two files. A job killed before it can run its
  trap leaves them too. A job that never stalls is cleaned by the wrapper after `wait`. The report's
  `Log:` line says the file is usually removed when the job ends. Cost: two small files created per job
  and two held handles in the watcher, no new process (unmeasured). In a wrapped run the watcher no longer polls for the beat file. Run by hand with no beat handle, it still tries one open a second.

## The Stop-time check

When a turn ends, a Stop hook runs `hooks/stall_watch.py --stop`. It reads the session transcript and
lists each open background shell and background agent that has been quiet longer than the age.
For a shell, the signal is its output file, and each log its
command names must be quiet too. A relative log resolves against the call record's `cwd`, after any sure `cd` the command makes (`named_logs`, above). A shell whose
output file is not found is listed as unknown. It prints one systemMessage that tells the model to stop
the shell or tell the owner. A job is listed once per crossing, at the first Stop after its stall crossed (see below).

If the shared names module fails to load, the check prints nothing. A false "still running" alarm is
worse than a missed stall, and the guard already refuses every call in that state (owner ruling,
2026-10-21). For a stalled background job, only the watcher's exit-3 report wakes an idle session. This
check runs at turn end, so it does not cover a job that stalls after the turn ends.

A job is listed only at the first Stop after its stall crossed. The crossing is its output file's mtime
(or the newest mark of a named log) plus the quiet age. The previous Stop is the timestamp of the newest
`stop_hook_summary` record in the transcript. The harness writes one after each Stop run. So the time
does not depend on how turns open. A queued prompt, an agent's hand-back and a hook's feedback all leave
turns that no prompt record marks. A summary whose run came right after a blocked Stop is skipped. That
Stop has hookErrors not empty, or preventedContinuation true. The next run had `stop_hook_active` true,
where the check prints nothing, so it listed nothing. A job whose crossing is not later than the
previous Stop was listed there, so it is silent now. A job that goes quiet again after new output crosses again, and is listed
again. An unknown job (no output file) is listed once, at the first Stop after its call: its call record's
time must be later than the previous Stop. Limit: a job whose output file existed at the previous Stop and
is gone now is not listed. With no summary, or a summary with no readable timestamp,
every quiet job is listed. The state is the transcript: no file is written.
Stop-side CPU rule: a shell job about to be listed is dropped when a process under it burns CPU, the
watcher's rule (posix with lsof only; `busy_outputs`). The job has no pid at Stop, so its processes are
those that hold its output file as stdout or stderr. Two `ps` reads 1.5 s apart tell whether CPU time advanced.
Stop-side unresolved-log rule: a listed job whose named log has an unknown directory says that log is
not watched, as the watcher's report does. The job is still listed when quiet. Limit: a spinning child is
never reported (the watcher counts CPU as life). A builtin spin in the job's shell is reported by the
watcher only: in a hook-wrapped job `tree_cpu` counts the job subshell, so Stop does not list it. Limit: a job
dropped as busy at its crossing Stop has used up its one listing, so a job busy and then hung is never listed by
Stop (the watcher still catches a hook-wrapped one). Limit (partial fix): one 1.5 s sample at whole-second `ps` resolution
reliably spares only CPU-bound jobs; a job at about 25% CPU can still be listed as quiet. Time bound: one
deadline of 6 s (`BUSY_BUDGET`) covers `lsof`, both `ps` reads and the wait. Each call's timeout is the time left.
Past the deadline the check returns none, and every job is listed as before. The Stop hook is killed at 10 s, so the check
stays well under it. Cost: no process
that lives on, no file, no timer. A quiet shell job whose output file a process holds costs at most one `lsof`,
two `ps` reads and a 1.5 s wait at that Stop. The `ps` reads run only when a process holds the file. A Stop that lists no shell job costs none.

Cost: one more JSON parse per `stop_hook_summary` line (one a Stop run), in the one pass that `scan_jobs`
already makes, at each Stop (unmeasured).

A background agent is a job too. Its launch record is a `toolUseResult` with `isAsync` true, status
`async_launched` and an `agentId`. `scan_jobs` reads it beside the shells, and the same notice and TaskStop
parsing closes it. Its transcript is `<dir of the session file>/<file stem>/subagents/agent-<id>.jsonl`,
built with `os.path`. The launch's `outputFile` is the fallback. The age is that file's mtime. A row names
the agent id and the remedy: stop it, then resume it by name, or send a fresh reviewer the prior report
(`roles-resume-by-name`). The listing rules are the shell's: once per crossing, against the previous Stop.
A transcript found in neither place is listed as unknown, once. An agent is not listed while any tool_use in the read window has no tool_result: that is one long call, not a stall. The check reads that from the end of the
transcript, for a quiet agent only. The read is the last 64 KB. It doubles until it holds a whole last
record. An empty transcript, or one whose every tool_use in the read window has its tool_result, is listed when quiet. A transcript that cannot be
read is listed.
Cost (`outcomes-mechanize-rules`): one `stat` per running agent at each Stop, and one read of the
transcript's end for each quiet agent not yet listed, pinned by `A8_cost_one_stat_per_running_agent_and_a_read_only_when_quiet` in
`hooks/test_stall_watch_stop.py`. No new process, timer or file.
Limits: a session that is idle with no Stop sees nothing until its next Stop. A TaskStop or a terminal
notice (completed, failed, killed or stopped) closes an agent id for the whole transcript. So an agent
stopped or finished, then resumed under the same id, is never listed again (debt `agent-resume-reads-closed`,
an agent resumed after it closed). An agent stuck inside one tool call is never listed: an open call has no
age cap (unmeasured). A model turn longer than the age would list a busy agent. Measured on 5 local agent transcripts
(559 records, 2026-11-07): the longest gap between records was 206 s, under the 300 s age.

The hook exits 0 and never refuses. A crash never refuses a call, as advisory hooks stay fail-open
(`guard-hooks-fail-closed`). It reuses the transcript parsing of the PreToolUse path, so that parsing has
one home (`building-one-home-per-capability`).

- Age: the default is 300 seconds, a builder's choice, checked only by the gap measure in the limits above. `STALL_WATCH_QUIET` sets another
  number of seconds.
- A job counts as finished when the transcript holds a completion notice with status completed, failed,
  killed or stopped (as a user record, or as an attachment record of type queued_command), or a
  "Successfully stopped task: <ID>" result of a TaskStop call.

Reason: the PreToolUse path runs only at a tool call, and on Windows it does nothing. No process id
exists for the job, so the age of its output file is the signal.

Kind: process
Home: hooks/stall_watch.py
