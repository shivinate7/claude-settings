# A background shell left open at turn end is reported

## The question

A background shell can stay open after a turn ends. Does the session learn of it?

## The ruling (owner, 2026-10-13 13:39 CDT)

The owner said: "Close it." When a turn ends, a Stop hook runs `hooks/stall_watch.py --stop`.

The hook reads the session transcript. It lists each background shell that is not finished
and whose output file has been quiet longer than the age (see Age). A shell whose output file is not found is listed as unknown. It prints one
systemMessage. The message tells the model to stop the shell or tell the owner.

The hook exits 0 and never blocks. A crash never refuses a call, as advisory hooks stay
fail-open (`gate-hooks-fail-closed`). It reuses the transcript parsing of the PreToolUse path
(`stall-watch`, the stall report ruling), so that parsing has one home (rule
building-one-home-per-capability).

## Why

The PreToolUse path runs only at a tool call. On Windows it does nothing. A shell can run
unnoticed to the end of a turn. No process id exists for the job, so the age of its output
file is the signal.

## Age

The default is 300 seconds. The builder chose that number. It is not measured.

Set `STALL_WATCH_QUIET` to another number of seconds. The owner may choose that number.

Test seams: `STALL_WATCH_NOW` sets the clock in epoch seconds. `STALL_WATCH_OUTPUT_BASE`
replaces the folder of each output path and keeps the file name.

## Finished jobs

A job counts as finished when the transcript holds one of these:

- a completion notice with status completed, failed, killed or stopped, as a user record;
- the same notice as an attachment record of type queued_command;
- a "Successfully stopped task: <ID>" result of a TaskStop call.

## Evidence (measured)

On 23 real local transcripts, the real mode raised 0 alarms. Those transcripts opened 128
background jobs. Of these, 126 closed by a completion notice and 2 by a TaskStop result.

Review rounds 1 and 2 found the three forms above in real transcripts. Each had caused a
false alarm before the check counted it.

## Holes, named

Each hole gives its cause, its effect, and the fix that closes it.

1. Cause: no dedupe. Effect: the message fires at every Stop while a job stays open. Fix:
   report each job ID once.
2. Cause: no age ceiling on open jobs. Effect: a job left from a resumed session reads as
   still running. Fix: add an age ceiling, past which an open job does not alarm.
3. Cause: the closing match also reads the text of user tool_result blocks. Effect: a
   tool_result that quotes a task-notification closes a job that is still running. Fix:
   count a notice only from a notice record, never from tool_result text.
4. Cause: the macOS CI jobs run no stop suite. Effect: the Stop path has no macOS run. Fix:
   add the stop suite step to the macOS jobs.
5. Cause: no run shows that a Stop systemMessage reaches the model. Effect: the alarm may
   never reach the model. decision_watch uses the same channel. Fix: in a live session, leave
   a job open at Stop and confirm the model receives the message.
6. Cause: the status match is case-sensitive, and a status outside the list counts as open.
   Effect: a job with a new or differently cased status never closes. Fix: match status
   without regard to case, and add each new final status to the list.
7. Cause: a list-form result closes a job only from its first text block. Effect: a
   multi-block result closes a job only when "Successfully stopped task" sits in the first
   block. Fix: search every text block of a list result.
8. Cause: os.stat raises ValueError on a path with a NUL byte, and the check does not catch
   it. Effect: every row for that run drops. Paths written by the harness cannot reach this.
   Fix: catch ValueError for each row, so one bad path drops one row.
9. Cause: the Windows CI step runs on a Windows runner that this change has not run on.
   Effect: the Windows CI result is unknown. Local runs passed. Fix: run the Windows stop suite
   step in CI and read its verdict.

## Tests

`hooks/test_stall_watch_stop.py` has 34 cases. Two steps named "Stall watch stop suite" in
`.github/workflows/gates.yml` run it, one on Linux and one on Windows.

Kind: process
Home: hooks/stall_watch.py
