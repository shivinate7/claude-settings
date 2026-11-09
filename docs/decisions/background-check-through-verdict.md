# A check runs through verdict, never into tail or head

## The ruling

No owner ruling yet. The coordinator asked for this guard rule after the incident below, under rule `building-guard-needs-incident` (a guard needs a mistake it stops). At 16:22 CST on 2026-11-07 the coordinator widened it. The merge tool's verdict calls are refused in the foreground too. A `merge --lane-lint` call piped into a filter hid the result twice that day. Roadmap step `guard-pipe-on-merge-lint` (merge verdict calls piped) holds that part. The owner may change either.

- A pipeline that holds a named check and a later `tail` or `head` stage is refused. The rule id is `check-tail`, in `hooks/guard_stream.py`.
- The merge tool's verdict calls are `merge --lane-lint` and `merge --review-record`. They are refused in the foreground and in the background.
- `merge --confirm` stays with the narrated-tail rule (`live-stream`, in the same file), so it is never refused twice. A plain `merge <pr>` preview, which returns in seconds, passes.
- `ci-job` is refused only in a call with `run_in_background`. In the foreground it passes.
- Filters between the check and the `tail` or `head` do not hide it: `merge --lane-lint 7 | grep -v DEBUG | tail -8` is refused.
- A `tee` stage between them does not end the check's reach: `merge --lane-lint 7 | tee x | tail -3` is refused, because `tail` still cuts what the agent reads, which is the incident's form (coordinator ruling, 2026-11-08 05:15 CST). A `tee` with no `tail` or `head` after it passes. `verdict` keeps the full log, so the remedy names it. A pipeline ends at any separator other than `|`.
- The remedy is `verdict <cmd>` with nothing after it (decision verdict-pipe-refused refuses a pipe out of it). It keeps the full log and prints the verdict itself.
- The rule reads the call at start, so a foreground `ci-job` the harness later moves to the background is not checked.
- The roster is named, as built:
  - `merge --lane-lint` and `merge --review-record`, in these spellings: `merge`, `merge.cmd`, and `merge/merge.py` or `merge/launch.py` run by `python`, any `python3.N`, `pythonw` or `py` (the roster read in `hooks/guard_stream.py`). Only the interpreter's script operand counts: its first word that is no flag, with `-W` and `-X` taking a value. `-m <module>` and `-c <code>` run no script, so `python3 -m pytest -k bin/ci-job` and `grep x merge/merge.py` are not the check.
  - A `uv run` ahead of any of these is read through, with the `uv` and `uv run` flags that take a value (`uv run --help`) and the global flags before `run`. So `uv run -w pytest merge --lane-lint 7`, `uv --quiet run merge --lane-lint 7`, `uv run python merge/merge.py --lane-lint 7` and `uv run merge/merge.py --lane-lint 7` are refused. The `.py` operand `uv run` runs with no interpreter word is read as the script, by the same reader as an interpreter's operand. The narrated rule (`live-stream`) reads through `uv run merge/merge.py` the same way, but not through `uv run merge`.
  - `ci-job`, in the background only, as the bullet above says. This is deliberate: every `ci-job` run prints one verdict per step, and a pipe into `tail` or `head` cuts them. An interpreter whose script operand ends in `bin/ci-job`, such as `python3 bin/ci-job checks --lint`, counts as `ci-job`.
- A call through `verdict`, including `python3 .../verdict`, is not a check-tail refusal, because a pipe after `verdict` is refused first by decision verdict-pipe-refused. So `verdict <cmd>` with nothing after it passes, behind any wrapper or `uv run`. A file read back later, and every other command piped into `tail`, pass.

Step `check-tail-wrapper-forms` added the `uv run`, `python3.N` and `bin/ci-job` forms, at the coordinator's request (2026-11-07 18:09 CST).

## The incident

Lane `notes-fix-other-2`, 2026-11-07, about 15:15 CST. The lane backgrounded `~/.claude/bin/merge --lane-lint 1476 2>&1 | tail -8`. Its verdict was lost.

- The lane said the stall watch ended the job. That cause is unverified: `hooks/stall_watch.py` only reports a quiet job and never kills it.
- The harm holds without that cause. `tail` holds all output until the command ends, then keeps 8 lines. A job that ends early, or is read early, shows nothing.

## Why a named roster

A rule on every `| tail` would refuse `make check 2>&1 | tail -40` and many other finished jobs. That is the guard that cries wolf (`guard-that-cries-wolf-is-spent`, a guard that cries wolf is spent). The system cannot say which commands print a verdict, so the roster names one entry per incident.

The rule stops a mistake Claude made in normal work (`guard-guards-mistakes-only`, guards stop Claude's mistakes, not an attacker). It reads no form that only an attacker would write.

## What check-tail reads

For an interpreter, check-tail reads the script operand only: the first word that is no flag. `grep -n x merge/merge.py` and `python3 -m pytest -k merge/merge.py` run no roster script, so they pass. An unquoted `$(` or backtick substitution splits into several words. So the operand reads on to the word that closes it. The roster tail is judged on the joined word (`_whole_word` in `hooks/guard_stream.py`).

## Known gaps

Each gap is one line in `docs/debts/notes.md`, under this decision. The lines are `check-tail-pipe-at-line-end`, `check-tail-no-nested-read`, `check-tail-powershell-select`, `check-tail-uv-flag-value`, `check-tail-trailing-amp` and `narrated-tail-no-uv`. No incident has shown any of them.

Why: a merge or lane verdict is the one line the orchestrator needs. A pipe into a truncating filter hides it, and the lane must run the check again.

Kind: process
Home: hooks/guard_stream.py
