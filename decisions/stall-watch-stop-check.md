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

Debts: `stall-message-repeats-every-stop` (the message fires at every Stop). `stall-open-job-no-age-ceiling` (an old open job reads as running). `stall-closes-on-quoted-notice` (a quoted notice closes a running job). `stall-macos-no-stop-suite` (the macOS jobs run no stop suite). `stall-message-delivery-unproven` (no run shows the Stop message reaches the model). `stall-list-result-first-block` (a list result closes from its first block). `stall-windows-ci-unknown` (the Windows CI result is unknown).

## Tests

`hooks/test_stall_watch_stop.py` has 34 cases. Two steps named "Stall watch stop suite" in
`.github/workflows/gates.yml` run it, one on Linux and one on Windows.

Kind: process
Home: hooks/stall_watch.py
