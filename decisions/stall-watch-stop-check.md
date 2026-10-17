# A background shell left open at turn end is reported

## The ruling

When a turn ends, a Stop hook runs `hooks/stall_watch.py --stop`. It reads the session transcript and
lists each background shell that is not finished and whose output file has been quiet longer than the
age. A shell whose output file is not found is listed as unknown. It prints one systemMessage that tells
the model to stop the shell or tell the owner.

The hook exits 0 and never blocks. A crash never refuses a call, as advisory hooks stay fail-open
(`gate-hooks-fail-closed`). It reuses the transcript parsing of the PreToolUse path (`stall-watch`), so
that parsing has one home (`building-one-home-per-capability`).

Reason: the PreToolUse path runs only at a tool call, and on Windows it does nothing. No process id
exists for the job, so the age of its output file is the signal.

**Age.** The default is 300 seconds, a builder's choice, not measured. `STALL_WATCH_QUIET` sets another
number of seconds. Test seams: `STALL_WATCH_NOW` sets the clock in epoch seconds.
`STALL_WATCH_OUTPUT_BASE` replaces the folder of each output path and keeps the file name.

**Finished jobs.** A job counts as finished when the transcript holds one of these:

- a completion notice with status completed, failed, killed or stopped, as a user record;
- the same notice as an attachment record of type queued_command;
- a "Successfully stopped task: <ID>" result of a TaskStop call.

Tests: `hooks/test_stall_watch_stop.py`. Two steps named "Stall watch stop suite" in
`.github/workflows/gates.yml` run it, one on Linux and one on Windows.

Kind: process
Home: hooks/stall_watch.py

## Holes, named

Debts: `stall-message-repeats-every-stop`, `stall-open-job-no-age-ceiling`, `stall-closes-on-quoted-notice`,
`stall-macos-no-stop-suite`, `stall-message-delivery-unproven`, `stall-list-result-first-block`,
`stall-windows-ci-unknown`.
