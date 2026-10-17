# A background shell left open at turn end is reported

## The ruling

When a turn ends, a Stop hook runs `hooks/stall_watch.py --stop`. It reads the session transcript and
lists each background shell that is not finished and whose output file has been quiet longer than the
age. A shell whose output file is not found is listed as unknown. It prints one systemMessage that tells
the model to stop the shell or tell the owner.

The hook exits 0 and never blocks. A crash never refuses a call, as advisory hooks stay fail-open
(`gate-hooks-fail-closed`). It reuses the transcript parsing of the PreToolUse path (`stall-watch`), so
that parsing has one home (`building-one-home-per-capability`).

- Age: the default is 300 seconds, a builder's choice, not measured. `STALL_WATCH_QUIET` sets another
  number of seconds.
- A job counts as finished when the transcript holds a completion notice with status completed, failed,
  killed or stopped (as a user record, or as an attachment record of type queued_command), or a
  "Successfully stopped task: <ID>" result of a TaskStop call.

Reason: the PreToolUse path runs only at a tool call, and on Windows it does nothing. No process id
exists for the job, so the age of its output file is the signal.

Kind: process
Home: hooks/stall_watch.py
