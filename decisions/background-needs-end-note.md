# A background server or watcher needs an end condition at start

## The question

How does a background server or watcher stop when its work ends?

## The incident

A q_max file server ran on port 3202 for 27 h. It was quiet for 99,352 s. No check stopped it.
The Stop quiet-shell check (`stall_watch --stop`, the Stop check, live since 2026-10-13 16:28)
caught it on its first chance.

## The ruling

Owner ruling, 2026-10-13 23:41 CDT: "End condition at start."

- A Bash or PowerShell call with `run_in_background` that starts a server or a watcher needs a
  note in its `description`: `until: <condition>`.
- The guard rule `background-end` in `hooks/guard_stream.py` refuses the call when the note is
  missing, or when its condition is empty.
- One-off builds, test runs and `gh run watch` pass without the note.
- The Stop check shows each quiet job's note beside it. The agent judges whether the job should
  still run.

## Why

A server or watcher can run long after its work ends. Nothing in the start call says when it
stops. A note at start gives the Stop check a condition to show. The protected outcome: no
background job runs unattended for a day with no stated reason.

## What protects it

- The guard refuses the call at start (rule `background-end`).
- The Stop check shows the note of each quiet job at turn end.

## Holes, named

- A foreground server that the harness moves to background at its 120 s timeout is not checked.
  Debt `timeout-moved-server-unchecked`: a foreground server moved to background at 120 s.

Kind: process
Home: hooks/guard_stream.py
Home: hooks/stall_watch.py
