# A check runs through verdict, never into a filter

## The ruling

No owner ruling yet. The coordinator asked for this guard rule after the incident below, under rule `building-guard-needs-incident` (a guard needs a mistake it stops). At 16:22 CST on 2026-11-07 the coordinator widened it. The merge tool's verdict calls are refused in the foreground too. A `merge --lane-lint` call piped into a filter hid the result twice that day. Roadmap step `guard-pipe-on-merge-lint` (merge verdict calls piped) holds that part. The owner may change either. The tee-then-tail form is a coordinator ruling, 2026-11-08 05:15 CST (process-only). The check reads any filter, not only `tail` and `head` (coordinator ruling, 2026-11-08 07:16 CST, process-only). The three Windows spellings, `tee.exe`, `Tee-Object` and `Out-File`, follow the 07:16 lone-`tee` ruling for their Windows forms (lane call, process-only; round 2 found a Windows false alarm).

- A pipeline that holds a named check and any later stage but a lone `tee`, `tee.exe`, `Tee-Object` or `Out-File` is refused: `tail`, `head`, `sed -n`, `grep -m1`, `awk` and the like. It reads the same pipeline walk as the narrated rule, with the filter test widened (`any_filter` in `_pipeline_hit`). The rule id is `check-tail`, in `hooks/guard_stream.py`.
- The merge tool's verdict calls are `merge --lane-lint` and `merge --review-record`. They are refused in the foreground and in the background.
- `merge --confirm` stays with the narrated-tail rule (`live-stream`, in the same file), so it is never refused twice. A plain `merge <pr>` preview, which returns in seconds, passes.
- The narrated-tail rule (`live-stream`, `narrated_tail_hit`) walks the same pipeline as this rule. It refuses a `merge --confirm` piped through any filter or chain of filters (`tee`, `grep`, `sed` and the like) into `tail` or `head`. `tail` or `head` cuts what the agent reads and hides the heartbeat until exit. Examples: `merge --confirm | tee x | tail -3`, `merge --confirm | grep FAIL | tail -3`, `merge --confirm | sed s/a/b/ | head -5`. A filter with no `tail` or `head` after it passes (coordinator ruling, 2026-11-08 06:47 CST). Its remedy names `verdict` or a `tee` with nothing after it.
- `ci-job` is refused only in the background: a call with `run_in_background`, or a pipeline closed by a trailing `&` (`ci-job checks --lint | grep FAIL & echo $!`, round 1 of the fresh review, 2026-11-08). In the foreground, with no `&`, it passes.
- A filter after the check is refused, with or without `tail` or `head` behind it: `merge --lane-lint 7 | sed -n 1,5p`, `merge --lane-lint 7 | grep -m1 FAIL`, `merge --review-record 7 | awk 'END{print}'`. No pipe, a redirect to a file, `verdict merge --lane-lint 7` and `grep -m1 FAIL lint.log` pass.
- A `tee` stage between them does not end the check's reach: `merge --lane-lint 7 | tee x | tail -3` is refused, because `tail` still cuts what the agent reads, which is the incident's form (coordinator ruling, 2026-11-08 05:15 CST). A `tee`, `tee.exe`, `Tee-Object` or `Out-File` with nothing after it passes. `verdict` keeps the full log, so the remedy names it. A pipeline ends at any separator other than `|`.
- The remedy is `verdict <cmd>` with nothing after it (decision verdict-pipe-refused refuses a pipe out of it). It keeps the full log and prints the verdict itself.
- The rule reads the call at start, so a foreground `ci-job` the harness later moves to the background is not checked.
- The roster is named, as built:
  - `merge --lane-lint` and `merge --review-record`, in these spellings only: `merge`, `merge.cmd`, and `merge/merge.py` or `merge/launch.py` run by `python`, `python3` or `py`, or run by their own path such as `./merge/merge.py` (`interpreter_only` in `hooks/guard_stream.py`). `uv run python merge/merge.py` and `python3.11 merge/merge.py` pass on this head; follow-up PR #1717 (check-tail-wrapper-forms) adds `uv run` and versioned pythons. A command that only names the script, such as `grep x merge/merge.py`, is not the check.
  - `ci-job`, in the background only (a call with `run_in_background`, or a trailing `&`). It rides on the `merge --lane-lint` incident, since lane lint runs `ci-job`. Every `ci-job` run prints one verdict per step, and a filter after it cuts them.
- A call through `verdict`, including `python3 .../verdict`, is not a check-tail refusal, because a pipe after `verdict` is refused first by decision verdict-pipe-refused. So `verdict <cmd>` with nothing after it passes. A file read back later, and every other command piped into `tail`, pass.

## The incident

Lane `notes-fix-other-2`, 2026-11-07, about 15:15 CST. The lane backgrounded `~/.claude/bin/merge --lane-lint 1476 2>&1 | tail -8`. Its verdict was lost.

- The lane said the stall watch ended the job. That cause is unverified: `hooks/stall_watch.py` only reports a quiet job and never kills it.
- The harm holds without that cause. `tail` holds all output until the command ends, then keeps 8 lines. A job that ends early, or is read early, shows nothing.

## Why a named roster

A rule on every `| tail` would refuse `make check 2>&1 | tail -40` and many other finished jobs. That is the guard that cries wolf (`guard-that-cries-wolf-is-spent`, a guard that cries wolf is spent). The system cannot say which commands print a verdict, so the roster names one entry per incident.

The rule stops a mistake Claude made in normal work (`guard-guards-mistakes-only`, guards stop Claude's mistakes, not an attacker). It reads no form that only an attacker would write.

## Known gaps

Each gap is one line in `docs/debts/notes.md`, under this decision. The lines are `check-tail-pipe-at-line-end`, `check-tail-no-nested-read` and `check-tail-any-filter-false-alarms`. No incident has shown any of them.

Why: a merge or lane verdict is the one line the orchestrator needs. A pipe into any filter after the run hides it, and the lane must run the check again.

Kind: process
Home: hooks/guard_stream.py
