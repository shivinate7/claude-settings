# A background check runs through verdict, never into tail or head

## The ruling

No owner ruling yet. The coordinator asked for this guard rule after the incident below, under rule `building-guard-needs-incident`. The owner may change it.

- A Bash call with `run_in_background` whose stage is a named check and whose next stage is `tail` or `head` is refused. The rule id is `background-check-tail`, in `hooks/guard_stream.py`.
- The remedy is `verdict <cmd>`. It keeps the full log and prints the verdict itself.
- A foreground call is never refused. The rule reads the call at start, so a foreground call the harness later moves to the background is not checked.
- The roster is named, as built:
  - `merge --lane-lint`, in every spelling of the narrating roster in `hooks/guard_stream.py` (`merge`, `merge.cmd`, `merge/merge.py` and `merge/launch.py`, run alone or through an interpreter).
  - `ci-job`, in any use.
- A call through `verdict` passes, including `python3 .../verdict`. `tee`, a file read back later, and every other command piped into `tail` pass.

## The incident

Lane `notes-fix-other-2`, 2026-11-07, about 15:15 CST. The lane backgrounded `~/.claude/bin/merge --lane-lint 1476 2>&1 | tail -8`. Its verdict was lost.

- The lane said the stall watch ended the job. That cause is unverified: `hooks/stall_watch.py` only reports a quiet job and never kills it.
- The harm holds without that cause. `tail` holds all output until the command ends, then keeps 8 lines. A job that ends early, or is read early, shows nothing.

## Why a named roster

A rule on every backgrounded `| tail` would refuse `make check 2>&1 | tail -40` and many other finished jobs. That is the guard that cries wolf (`guard-that-cries-wolf-is-spent`). The system cannot say which commands print a verdict, so the roster names one entry per incident.

The rule stops a mistake Claude made in normal work (`guard-guards-mistakes-only`). It reads no form that only an attacker would write.

Why: a lane's verdict is the one line the orchestrator needs. A pipe into a truncating filter hides it, and the lane must run the check again.

Kind: process
Home: hooks/guard_stream.py
