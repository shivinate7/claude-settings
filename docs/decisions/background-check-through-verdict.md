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
  - `merge --lane-lint` and `merge --review-record`, in every spelling of the narrating roster in `hooks/guard_stream.py`: `merge`, `merge.cmd`, and `merge/merge.py` or `merge/launch.py` run by `python`, any `python3.N`, `pythonw` or `py`. Only the script the command runs counts: an interpreter's first word that is no flag (`-W` and `-X` take a value), or the path a `-m <module>` names (`merge.merge` is `merge/merge.py`). `-c <code>` runs no script, so `python3 -m pytest -k bin/ci-job` and `grep x merge/merge.py` are not the check.
  - A `uv run` ahead of any of these is read through, with the `uv` and `uv run` flags that take a value (`uv run --help`) and the global flags before `run`. So `uv run -w pytest merge --lane-lint 7`, `uv --quiet run merge --lane-lint 7` and `uv run python merge/merge.py --lane-lint 7` are refused. So are the forms below. The narrated rule (`live-stream`) does not read through `uv`.
  - `ci-job`, in the background only, as the bullet above says. This is deliberate: every `ci-job` run prints one verdict per step, and a pipe into `tail` or `head` cuts them. An interpreter whose script operand ends in `bin/ci-job`, such as `python3 bin/ci-job checks --lint`, counts as `ci-job`.
- A call through `verdict` passes `check-tail` behind every wrapper: `env FOO=1 verdict ...`, `uv run verdict ...`, `python3 .../verdict`, `verdict.cmd`. Rule `verdict-pipe-exit`, below, reads such a call. A file read back later, and every other command piped into `tail`, pass.
- Four more forms are read. `check-tail` and `verdict-pipe-exit` read them through the same helpers (`_script_run`, `_merge_flag`), so neither copies a roster:
  - `uv run <path>.py`: uv runs a `.py` operand as a script, so after `uv run` a command word that ends `.py` is the script (`uv run merge/merge.py --lane-lint 7 | tail`).
  - A script run straight by its path (`./lint/ste_lint.py`, `./merge/merge.py`): the command word is the script.
  - The module form (`python3 -m lint.ste_lint`, `python3 -m merge.merge --lane-lint 7`): the module name is mapped to its path and read as a script operand. A cluster such as `-Im` is read too.
  - An argparse prefix: `merge --lane`, `--lane-l` and `--review-r` mean `--lane-lint` and `--review-record`. An ambiguous prefix (`--l` matches `--lane-lint`, `--lint-unknown-ok` and `--live`) is an argparse error and runs no check, so it passes. The option names are `MERGE_OPTIONS` in `hooks/merge_options.py`. A test compares it with the options of `build_parser()` in `merge/merge.py`, and the guard reads it, so the guard never imports or runs the merge tool. No runtime check sits in the merge tool, because `--help` and `--unlock` must not depend on one.

Step `check-tail-wrapper-forms` added the `uv run`, `python3.N` and `bin/ci-job` forms, at the coordinator's request (2026-11-07 18:09 CST).

- The guard-set lists (the install.sh copy loop, the install.ps1 copy and set loops, and the ci-scope.sh case) now hold every module the guard imports, at load time or lazily in a function body: `override.py` and `_nowindow.py` joined the earlier ones. A module missing from a list fails its import in the shipped guard, which drops the owner override lift and the no-window spawn. The check `guardset4` derives that set from the imports of `guard.py` and each `guard_*.py`, so a new import needs no edit to it (coordinator request, 2026-11-08 02:23 CST).

## A verdict call piped onward

The coordinator asked for rule `verdict-pipe-exit` at 18:39 CST on 2026-11-07, as step `verdict-pipe-exit`. The owner may change it.

The coordinator widened it at 23:38 CST on 2026-11-07, as step `guard-pipe-on-merge-lint`: a lint command run without `verdict` is refused like a verdict call, with the lint forms below.

Ruling (coordinator, 2026-11-07 19:09 CST, option a: "my brief was wrong on `;`"): the rule does not refuse `;`. It keeps `&&` and `||`.

Incident: lane `silent-undo-reads-retire-run` ran `~/.claude/bin/verdict python3 lint/ste_lint.py <file> 2>&1 | tail -1 && git add ... && git commit ...`. Commit 7ae6f0e1c went in with a hidden lint error.

Incident, lint forms: a lane ran `ste_lint ... | tail`, then a commit and a push, and the pipe masked the lint's exit. Commit b613b336c on PR #1754 went up with an STE error. The coordinator asked for the lint commands to be refused the same way.

Harm: a pipeline's exit status is its last stage's. `verdict` prints FAIL and exits non-zero, `tail` exits 0, so the `&&` after it runs. The check protects nothing.

- A pipeline whose first stage is a `verdict` call (any spelling, behind any wrapper or `uv run`) and that has a later stage is refused when `&&` or `||` follows it and another command comes after. The rule id is `verdict-pipe-exit`, in `hooks/guard_stream.py`.
- A pipeline whose first stage is a lint command run without `verdict` is refused the same way: it has a later stage, `&&` or `||` follows, and the last `set` left pipefail off. The lint commands are `ste_lint` (a script whose basename is `ste_lint.py`, so `cd lint && ./ste_lint.py x.md` counts; run by an interpreter, by its path, by `uv run` or as a `-m` module), `ste-changed` (any path, `.cmd` too), `ci-job` with `--lint`, and `merge --lane-lint`. They are read through the same wrappers as `check-tail`: `uv run <command>` (such as `uv run python`, `uv run ste-changed` or `uv run ci-job --lint`), `env` and the python forms. A `merge --lane-lint` pipe into `tail` or `head` is refused by `check-tail` first. The forms that reach this rule are `merge --lane-lint` piped into another filter, such as `grep`.
- The rule id stays `verdict-pipe-exit`. One id names one harm, a hidden check exit, so the owner's off switch and the guard log keep one name. The reason text says the lint forms are covered.
- It is refused in the foreground and in the background.
- `set -o pipefail` (or a cluster such as `set -euo pipefail`) earlier in the same command passes. The last `set` that sets or clears pipefail before the pipeline decides, so `set +o pipefail` after `set -o pipefail` does not pass.
- A `;` after the pipeline is not read. Without `set -e`, the next command runs after a red check with or without the pipe. Under `set -e`, the pipe hides the failure and the next command runs: a known gap, note verdict-pipe-newline.
- A bare `verdict <cmd>`, `verdict <cmd> && ...` with no pipe, and a verdict pipe that is the command's last pass.
- The remedy is to run `verdict <cmd>` with no pipe, or to set pipefail first.

## The incident

Lane `notes-fix-other-2`, 2026-11-07, about 15:15 CST. The lane backgrounded `~/.claude/bin/merge --lane-lint 1476 2>&1 | tail -8`. Its verdict was lost.

- The lane said the stall watch ended the job. That holds for the wrapper, not the job. A background command runs inside a wrapper that relays its log through `hooks/stall_watch.py`. When the watch reports a quiet job, the wrapper exits 3 and stops relaying. The job keeps running, and its exit trap deletes the log when it ends. So the output after the stall reaches no reader, and `tail` kept nothing either. Read 2026-11-08 00:21 CST from the wrapper command of a stopped background task.
- `verdict` avoids this: it writes a heartbeat to the beat file, so the watch sees no stall, and it keeps the full log in its own file.
- The harm holds without that cause. `tail` holds all output until the command ends, then keeps 8 lines. A job that ends early, or is read early, shows nothing.

The coordinator asked for the four forms at 00:34 CST on 2026-11-08. The owner's rule, ruled at 13:20 CST on 2026-11-07, is "a gap gets a fix, not a note".

## Why a named roster

A rule on every `| tail` would refuse `make check 2>&1 | tail -40` and many other finished jobs. That is the guard that cries wolf (`guard-that-cries-wolf-is-spent`, a guard that cries wolf is spent). The system cannot say which commands print a verdict, so the roster names one entry per incident.

The rule stops a mistake Claude made in normal work (`guard-guards-mistakes-only`, guards stop Claude's mistakes, not an attacker). It reads no form that only an attacker would write.

## Known gaps

Each gap is one line in `docs/debts/notes.md`, under this decision. The lines are `check-tail-pipe-at-line-end`, `check-tail-no-nested-read`, `check-tail-powershell-select`, `check-tail-trailing-amp`, `verdict-pipe-if`, `verdict-pipe-substitution` and `narrated-tail-no-uv`. No incident has shown any of them.

Why: a merge or lane verdict is the one line the orchestrator needs. A pipe into a truncating filter hides it, and the lane must run the check again.

Kind: process
Home: hooks/guard_stream.py
