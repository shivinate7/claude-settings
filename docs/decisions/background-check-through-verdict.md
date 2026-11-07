# A check runs through verdict, never into tail or head

## The ruling

No owner ruling yet. The coordinator asked for this guard rule after the incident below, under rule `building-guard-needs-incident` (a guard needs a mistake it stops). At 16:22 CST on 2026-11-07 the coordinator widened it. The merge tool's verdict calls are refused in the foreground too. A `merge --lane-lint` call piped into a filter hid the result twice that day. Roadmap step `guard-pipe-on-merge-lint` (merge verdict calls piped) holds that part. The owner may change either.

- A pipeline that holds a named check and a later `tail` or `head` stage is refused. The rule id is `check-tail`, in `hooks/guard_stream.py`.
- The merge tool's verdict calls are `merge --lane-lint` and `merge --review-record`. They are refused in the foreground and in the background.
- `merge --confirm` stays with the narrated-tail rule (`live-stream`, in the same file), so it is never refused twice. A plain `merge <pr>` preview, which returns in seconds, passes.
- `ci-job` is refused only in a call with `run_in_background`. In the foreground it passes.
- Filters between the check and the `tail` or `head` do not hide it: `merge --lane-lint 7 | grep -v DEBUG | tail -8` is refused.
- A `tee` stage between them ends the check's reach, because `tee` keeps every byte. A pipeline ends at any separator other than `|`.
- The remedy is `verdict <cmd>`. It keeps the full log and prints the verdict itself.
- The rule reads the call at start, so a foreground `ci-job` the harness later moves to the background is not checked.
- The roster is named, as built:
  - `merge --lane-lint` and `merge --review-record`, in every spelling of the narrating roster in `hooks/guard_stream.py`: `merge`, `merge.cmd`, and `merge/merge.py` or `merge/launch.py` run by `python`, `python3` or `py`. A command that only names the script, such as `grep x merge/merge.py`, is not the check.
  - `ci-job`, in any use. This is deliberate: every `ci-job` run prints one verdict per step, and a pipe into `tail` or `head` cuts them.
- A call through `verdict` passes, including `python3 .../verdict`. A file read back later, and every other command piped into `tail`, pass.

## The incident

Lane `notes-fix-other-2`, 2026-11-07, about 15:15 CST. The lane backgrounded `~/.claude/bin/merge --lane-lint 1476 2>&1 | tail -8`. Its verdict was lost.

- The lane said the stall watch ended the job. That cause is unverified: `hooks/stall_watch.py` only reports a quiet job and never kills it.
- The harm holds without that cause. `tail` holds all output until the command ends, then keeps 8 lines. A job that ends early, or is read early, shows nothing.

## Why a named roster

A rule on every `| tail` would refuse `make check 2>&1 | tail -40` and many other finished jobs. That is the guard that cries wolf (`guard-that-cries-wolf-is-spent`, a guard that cries wolf is spent). The system cannot say which commands print a verdict, so the roster names one entry per incident.

The rule stops a mistake Claude made in normal work (`guard-guards-mistakes-only`, guards stop Claude's mistakes, not an attacker). It reads no form that only an attacker would write.

## Known gaps

Each gap is one line in `docs/debts/notes.md`, under this decision. The lines are `check-tail-pipe-at-line-end`, `check-tail-no-nested-read`, `check-tail-powershell-select` and `check-tail-trailing-amp`. No incident has shown any of them.

Why: a merge or lane verdict is the one line the orchestrator needs. A pipe into a truncating filter hides it, and the lane must run the check again.

Kind: process
Home: hooks/guard_stream.py
