# A check runs through verdict, never into a filter

## The ruling

No owner ruling yet. The coordinator asked for this guard rule after the incident below, under rule `building-guard-needs-incident` (a guard needs a mistake it stops). At 16:22 CST on 2026-11-07 the coordinator widened it. The merge tool's verdict calls are refused in the foreground too. A `merge --lane-lint` call piped into a filter hid the result twice that day. Roadmap step `guard-pipe-on-merge-lint` (merge verdict calls piped) holds that part. The owner may change either. The tee-then-tail form is a coordinator ruling, 2026-11-08 05:15 CST (process-only). The check reads any filter, not only `tail` and `head`, after `merge --lane-lint`, `merge --review-record` and a backgrounded `ci-job` (coordinator ruling, 2026-11-08 07:16 CST, process-only). `merge --release-check` keeps the `tail` and `head` reach. The owner has not ruled whether it widens too.

- A pipeline that holds a named check and a later filter that cuts what the agent reads is refused. For `merge --lane-lint`, `merge --review-record` and a backgrounded `ci-job`, every later stage counts but a lone `tee`, `tee.exe`, `Tee-Object` or `Out-File` (`any_filter` in `_pipeline_hit`, `FILE_WRITER_STAGES`): `sed -n`, `grep -m1`, `awk` and `Select-Object -Last` cut what the agent reads as `tail` does. For `merge --release-check`, only `tail` and `head` count. The rule id is `check-tail`, in `hooks/guard_stream.py`.
- The merge tool's verdict calls are `merge --lane-lint`, `merge --review-record` and `merge --release-check`. They are refused in the foreground and in the background. A flag is read as its exact name or as `--name=value`. The merge tool takes no prefix of a flag (`allow_abbrev` is off, decision merge-confirm-repo), so `merge --lane 7`, which runs nothing, is not read as `--lane-lint`.
- `merge --confirm` stays with the narrated-tail rule (`live-stream`, in the same file), so it is never refused twice. A plain `merge <pr>` preview, which returns in seconds, passes.
- `ci-job` is refused only in the background: a call with `run_in_background`, or a pipeline whose list a job `&` ends, spaced or glued to the last word (`ci-job checks --lint | grep FAIL & echo $!`, `ci-job checks | tail -3&`, `ci-job x | tail && echo done & echo $!`). One reader, `backgrounding_amp` in `hooks/guard_core.py`, serves this rule and `detached-launch`. `detached-launch` refuses the call first when no pid is captured, so this rule names the job when `$!` is. It skips the `&` of `|&`, `&&`, `>&` and `2>&1`, a quoted `&`, and a `&` in arithmetic or a PowerShell call operator. In the foreground, with no `&`, `ci-job` passes.
- A filter after the check is refused, with or without `tail` or `head` behind it: `merge --lane-lint 7 | sed -n 1,5p`, `merge --lane-lint 7 | grep -m1 FAIL`, `merge --review-record 7 | awk 'END{print}'`. No pipe, a redirect to a file, `verdict merge --lane-lint 7` and `grep -m1 FAIL lint.log` pass.
- A `tee` stage between them does not end the check's reach: `merge --lane-lint 7 | tee x | tail -3` is refused, because `tail` still cuts what the agent reads, which is the incident's form. A `tee`, `tee.exe`, `Tee-Object` or `Out-File` with nothing after it passes. `verdict` keeps the full log, so the remedy names it. A pipeline ends at any separator other than `|`.
- A lint script piped into any later command is refused when a later pipeline of the same call runs `git commit` or `git push`. `tail`, `head`, `grep`, `tee` and `wc` all count: the gate reads the exit, and a pipeline's exit is its last stage's. The lone-`tee` pass above is about cut output, so it does not apply here (lane reading, no owner or coordinator ruling; process-only). A script is a `.py` under `lint/` run by an interpreter, as `-m lint.<name>`, or run directly as the `.py` command word, with or without `uv run`. It is read by the same reader of the script as the roster (`_script_run` in `hooks/guard_stream.py`). After a `cd lint` earlier in the call, a script named by its basename (`cd lint && ./ste_lint.py x.md | tail -3 && git commit -m x`) is a lint script while the last `cd` target ends in `lint`. A `cd` elsewhere ends it, and the word must be a word of the call, so `cd lint && python3 -m pytest | tail && git commit` passes. The same lint piped with no commit or push after it passes. So do `verdict <lint>` then a commit, a lint with no pipe then a commit, and a commit before the lint. The `git commit` and `git push` words are read by the one reader of git calls (`git_calls` in `hooks/guard_core.py`). The incident is lane `windows-tests-for-touched-files`, 2026-11-08 07:12 CST: a lint piped to `tail`, then a commit, in one call. `ste_lint` exited 1, `tail` returned 0, and the commit and push ran.
- The remedy is `verdict <cmd>` with nothing after it (decision verdict-pipe-refused refuses a pipe out of it). It keeps the full log and prints the verdict itself.
- The rule reads the call at start, so a foreground `ci-job` the harness later moves to the background is not checked.
- The roster is named, as built:
  - `merge --lane-lint` and `merge --review-record`, in these spellings: `merge`, `merge.cmd`, and `merge/merge.py` or `merge/launch.py` run by `python`, any `python3.N`, `pythonw` or `py` (the roster read in `hooks/guard_stream.py`). Only the interpreter's script operand counts: its first word that is no flag, with `-W` and `-X` taking a value. `-m <module>` reads as the module's file, in any flag spelling (`-Im`, `-W ignore -m`, `-mlint.x`), so `python3 -m merge.merge --lane-lint 7 | tail` is refused. `python3 -m pytest -k bin/ci-job` and `grep x merge/merge.py` are not the check, and `-c <code>` runs no script.
  - A `uv run` ahead of any of these is read through, with the `uv` and `uv run` flags that take a value (`uv run --help`) and the global flags before `run`. So `uv run -w pytest merge --lane-lint 7`, `uv --quiet run merge --lane-lint 7`, `uv run python merge/merge.py --lane-lint 7` and `uv run merge/merge.py --lane-lint 7` are refused. The `.py` operand `uv run` runs with no interpreter word is read as the script, by the same reader as an interpreter's operand. The narrated rule (`live-stream`) reads through `uv run merge/merge.py` the same way, but not through `uv run merge`.
  - `ci-job`, in the background only, as the bullet above says. This is deliberate: every `ci-job` run prints one verdict per step, and a filter after it cuts them. An interpreter whose script operand ends in `bin/ci-job`, such as `python3 bin/ci-job checks --lint`, counts as `ci-job`.
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

For an interpreter, check-tail reads the script operand only: the first word that is no flag. `grep -n x merge/merge.py` and `python3 -m pytest -k merge/merge.py` run no roster script, so they pass. (`-m <module>` reads as the module's file; see the roster above.) An unquoted `$(` or backtick substitution splits into several words. So the operand reads on to the word that closes it. The roster tail is judged on the joined word (`_whole_word` in `hooks/guard_stream.py`).

## Known gaps

Each gap is one line in `docs/debts/notes.md`, under this decision. The lines are `check-tail-pipe-at-line-end`, `check-tail-no-nested-read`, `check-tail-any-filter-false-alarms`, `check-tail-lint-commit-limits`, `check-tail-uv-flag-value`, `narrated-tail-no-uv`, `check-tail-assign-then-amp` and `check-tail-pipefail-false-alarm`. No incident has shown any of them.

Why: a merge or lane verdict is the one line the orchestrator needs. A pipe into any filter after the run hides it, and the lane must run the check again.

Kind: process
Home: hooks/guard_stream.py
