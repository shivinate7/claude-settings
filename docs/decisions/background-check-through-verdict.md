# A check runs through verdict, never into tail or head

## The ruling

No owner ruling yet. The coordinator asked for this guard rule after the incident below, under rule `building-guard-needs-incident` (a guard needs a mistake it stops). At 16:22 CST on 2026-11-07 the coordinator widened it. The merge tool's verdict calls are refused in the foreground too. A `merge --lane-lint` call piped into a filter hid the result twice that day. Roadmap step `guard-pipe-on-merge-lint` (merge verdict calls piped) holds that part. The owner may change either.

- A pipeline that holds a named check and a later `tail` or `head` stage is refused. The rule id is `check-tail`, in `hooks/guard_stream.py`.
- The merge tool's verdict calls are `merge --lane-lint` and `merge --review-record`. They are refused in the foreground and in the background.
- `merge --confirm` stays with the narrated-tail rule (`live-stream`, in the same file), so it is never refused twice. A plain `merge <pr>` preview, which returns in seconds, passes.
- `ci-job` is refused only in a call with `run_in_background`. In the foreground it passes.
- Filters between the check and the `tail` or `head` do not hide it: `merge --lane-lint 7 | grep -v DEBUG | tail -8` is refused.
- A `tee` stage between them does not end the check's reach: `merge --lane-lint 7 | tee x | tail -3` is refused, because `tail` still cuts what the agent reads, which is the incident's form (coordinator ruling, 2026-11-08 05:15 CST). A `tee` with no `tail` or `head` after it passes. `verdict` keeps the full log, so the remedy names it. A pipeline ends at any separator other than `|`.
- A lint script piped into any later command is refused when a later pipeline of the same call runs `git commit` or `git push`. `tail`, `head`, `grep`, `tee` and `wc` all count: the gate reads the exit, and a pipeline's exit is its last stage's. The lone-`tee` pass above is about cut output, so it does not apply here (lane call, process-only). A script is a `.py` under `lint/` run by an interpreter, or run directly as the `.py` command word, with or without `uv run`. It is read through the same wrappers and `uv run` as the roster, by the same reader of the script (`_script_run` in `hooks/guard_stream.py`). The last stage's exit hides a red lint, so the commit or push runs on it. Incident: lane `windows-tests-for-touched-files`, 2026-11-08 07:12 CST. A lint piped to `tail`, then a commit, in one call: `ste_lint` exited 1, `tail` returned 0, and the commit and push ran. A redirect word before the command, a substitution in the script path, and a pipe inside `$(…)` count too. Each `$(…)` text is read apart (`_substitutions`, as `verdict_pipe_hit` reads it). Order across texts is not tracked: a lint, inside a substitution or outside, counts when any other text of the call runs a commit or a push. So `lint | tail -2 && out=$(git commit ...)` is refused. A segment of only redirects (`> out.txt`) names no command and reads as no stage. The same lint piped with no commit or push after it passes, as do `verdict <lint>` then a commit, and a lint with no pipe then a commit. The `git commit` and `git push` words are read by the one reader of git calls (`git_calls` in `hooks/guard_core.py`).
- The remedy is `verdict <cmd>` with nothing after it (decision verdict-pipe-refused refuses a pipe out of it). It keeps the full log and prints the verdict itself.
- The rule reads the call at start, so a foreground `ci-job` the harness later moves to the background is not checked.
- The roster is named, as built:
  - `merge --lane-lint` and `merge --review-record`, in these spellings: `merge`, `merge.cmd`, and `merge/merge.py` or `merge/launch.py` run by `python`, any `python3.N`, `pythonw` or `py` (the roster read in `hooks/guard_stream.py`). Only the interpreter's script operand counts: its first word that is no flag and no redirect word, with `-W` and `-X` taking a value. `-m <module>` and `-c <code>` run no script, so `python3 -m pytest -k bin/ci-job` and `grep x merge/merge.py` are not the check.
  - A `uv run` ahead of any of these is read through, with the `uv` and `uv run` flags that take a value (`uv run --help`) and the global flags before `run`. So `uv run -w pytest merge --lane-lint 7`, `uv --quiet run merge --lane-lint 7`, `uv run python merge/merge.py --lane-lint 7` and `uv run merge/merge.py --lane-lint 7` are refused. The `.py` operand `uv run` runs with no interpreter word is read as the script, by the same reader as an interpreter's operand. The narrated rule (`live-stream`) reads through `uv run merge/merge.py` the same way, but not through `uv run merge`.
  - `ci-job`, in the background only, as the bullet above says. This is deliberate: every `ci-job` run prints one verdict per step, and a pipe into `tail` or `head` cuts them. An interpreter whose script operand ends in `bin/ci-job`, such as `python3 bin/ci-job checks --lint`, counts as `ci-job`.
- A call through `verdict`, including `python3 .../verdict`, is not a check-tail refusal, because a pipe after `verdict` is refused first by decision verdict-pipe-refused. So `verdict <cmd>` with nothing after it passes, behind any wrapper or `uv run`. A file read back later, and every other command piped into `tail`, pass.
- Five more forms are read, through the same helpers (`_script_run`, `_merge_flag`), so the check never copies a roster:
  - `uv run <path>.py`: uv runs a `.py` operand as a script, so after `uv run` a command word that ends `.py` is the script (`uv run merge/merge.py --lane-lint 7 | tail`).
  - A script run straight by its path (`./merge/merge.py`): the command word is the script.
  - A module run, `-m lint.<name>` or `-m merge.merge`, in any flag spelling (`-Im`, `-W ignore -m`, `-mlint.x`): the module reads as its file, `lint/<name>.py` or `merge/merge.py`, in `_script_operand`, so the lint and roster tails judge it as they judge the path. `python3 -m pytest` is no script of either and passes. `-c` runs no script.
  - A lint script named by its basename after a `cd lint` earlier in the same call (`cd lint && ./ste_lint.py x.md | tail -3 && git commit -m x`): `lint_stage` reads the script as `lint/<name>.py` while the last `cd`, `pushd` or `set-location` target ends in `lint`. A later `cd` elsewhere ends it. A script path with a directory in it is judged as written.
  - An argparse prefix: `merge --lane`, `--lane-l` and `--review-r` mean `--lane-lint` and `--review-record`. An ambiguous prefix (`--l` matches `--lane-lint`, `--lint-unknown-ok` and `--live`) is an argparse error and runs no check, so it passes. The option names are `MERGE_OPTIONS` in `hooks/merge_options.py`. A test compares it with the options of `build_parser()` in `merge/merge.py`, and the guard reads it, so the guard never imports or runs the merge tool. No runtime check sits in the merge tool, because `--help` and `--unlock` must not depend on one.

Step `check-tail-wrapper-forms` added the `uv run`, `python3.N` and `bin/ci-job` forms, at the coordinator's request (2026-11-07 18:09 CST).

## The incident

Lane `notes-fix-other-2`, 2026-11-07, about 15:15 CST. The lane backgrounded `~/.claude/bin/merge --lane-lint 1476 2>&1 | tail -8`. Its verdict was lost.

- The lane said the stall watch ended the job. That holds for the wrapper, not the job. A background command runs inside a wrapper that relays its log through `hooks/stall_watch.py`. When the watch reports a quiet job, the wrapper exits 3 and stops relaying. The job keeps running, and its exit trap deletes the log when it ends. So the output after the stall reaches no reader, and `tail` kept nothing either. Read 2026-11-08 00:21 CST from the wrapper command of a stopped background task.
- `verdict` avoids this: it writes a heartbeat to the beat file, so the watch sees no stall, and it keeps the full log in its own file.
- The harm holds without that cause. `tail` holds all output until the command ends, then keeps 8 lines. A job that ends early, or is read early, shows nothing.

The coordinator asked for the three forms at 00:34 CST on 2026-11-08. The owner's rule, ruled at 13:20 CST on 2026-11-07, is "a gap gets a fix, not a note".

## Why a named roster

A rule on every `| tail` would refuse `make check 2>&1 | tail -40` and many other finished jobs. That is the guard that cries wolf (`guard-that-cries-wolf-is-spent`, a guard that cries wolf is spent). The system cannot say which commands print a verdict, so the roster names one entry per incident.

The rule stops a mistake Claude made in normal work (`guard-guards-mistakes-only`, guards stop Claude's mistakes, not an attacker). It reads no form that only an attacker would write.

## What check-tail reads

For an interpreter, check-tail reads the script operand only: the first word that is no flag and no redirect word. `grep -n x merge/merge.py` and `python3 -m pytest -k merge/merge.py` run no roster script, so they pass. (`-m <module>` reads as the module's file; see the module bullet above.) An unquoted `$(` or backtick substitution splits into several words. So the operand reads on to the word that closes it. The operand reads on to the closing word, and the roster tail is judged on the joined word (`_whole_word` in `hooks/guard_stream.py`). Each `$(…)` text is read apart first (`_substitutions`), so `python3 $(git rev-parse --show-toplevel | head -1)/merge/merge.py --lane-lint 7 | tail` is refused (owner ruling 2026-11-07 13:20 CST: a gap gets a fix).

A redirect word is skipped, because the shell strips it before the interpreter runs. Redirect words are `2>&1`, `2>/dev/null`, `>file`, `>>file`, `<file` and `&>file`. A bare operator such as `2>` also skips the word after it. So `python3 -u 2>&1 merge/merge.py --lane-lint 7 | tail -3` is refused, as are `python3 2>/dev/null merge/merge.py --review-record 7 | head -5` and `uv run lint/ste_lint.py docs/x.md | tail -2; git commit -m m`. Without the skip, the redirect word read as the script and hid the merge script from the check.

## Known gaps

Each gap is one line in `docs/debts/notes.md`, under this decision. The lines are `check-tail-pipe-at-line-end`, `check-tail-no-nested-read`, `check-tail-powershell-select`, `check-tail-uv-flag-value`, `check-tail-trailing-amp` and `narrated-tail-no-uv`. No incident has shown any of them.

Why: a merge or lane verdict is the one line the orchestrator needs. A pipe into a truncating filter hides it, and the lane must run the check again.

Kind: process
Home: hooks/guard_stream.py
