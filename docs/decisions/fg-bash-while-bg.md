---
id: pending
slug: fg-bash-while-bg
---

# A long foreground command waits in the background while the session's agents and background commands run

## The ruling

Owner, 2026-11-16 13:47 CST: "refuse only commands that can run long, such as tests, lint, merges, builds and installs, or anything asking a time limit over 60 s. Quick reads stay in the foreground."

Owner, 2026-11-25 18:33 CST, on option (a), "Exempt merge from the foreground rule": "approved kind of, shouldn't it automatically go to the background in 2 minutes? ORR we spawn a session with the objective of just merging and then ending that session?"

Mistake: a session ran a long command in the foreground while its agents and background commands ran. The call held the session still. No notice from that work could be read until the call ended.

## Answer to the owner's question

- The harness moves a foreground Bash call to the background at its 120 s timeout (`docs/debts/notes.md`, entry `timeout-moved-server-unchecked`).
- The merge deadline is 45 min by default (`merge/merge.py:2760`). This repo's stamp sets 80 (`.github/stamp.json:7`). The tool reads that stamp by default (`merge/merge.py:2241`).
- A session that only merges is not built.

## The rule

- The guard rule `fg-bash-while-bg` in `hooks/guard_stream.py` refuses a Bash or PowerShell call that is in the foreground, can run long, and is made while this session has background work. A short merge tool call is exempt (below).
- Refusal text: "refused in the foreground while background work runs"; rerun it with `run_in_background` and it is allowed.
- Background work is a background command or a background agent with no terminal task notice and no TaskStop result. `scan_jobs` in `hooks/stall_watch.py` reads it from the transcript. It is the one reader of that state.
- A call can run long when one command in it is a test run (pytest, unittest, jest, vitest, a `test_*` script), a lint, a `merge` run that is not a short merge tool call (below), a build (make, xcodebuild, cargo, go, gradle, a package script named build), an install (pip, npm, brew, apt), or a `verdict` run. A `timeout` over 60000 ms counts too, even on a quick read. The roster is `FG_PROGRAMS` and its neighbours in `hooks/guard_stream.py`.
- A call is read by command word and shape, never by substring. `git status`, `cat`, `grep` and `ls` stay in the foreground.
- A call that sets `run_in_background`, a call from an agent, and a call made when the transcript is missing or unreadable all pass. A missing transcript fails open, as the question box does.
- The rule judges the PowerShell tool the same as Bash.
- Order: it runs before `check-timeout` (`background-check-through-verdict`). A foreground `merge --lane-lint` under background work gets this refusal. Its rerun in the background then meets `check-timeout`'s limit. With no background work, `check-timeout` is unchanged.

## The merge exemption

- A short merge tool call passes in the foreground under background work. The calls are `merge N --ready`, `merge N --confirm` and `merge N --express`, with `-C PATH` or `--repo-dir PATH`, `--session NAME` and `--head SHA`, in any order.
- The call needs a PR number. A value flag with no value, or a value that starts with `-`, is refused.
- Other bare words pass as values split off a substitution, such as `$(git rev-parse HEAD)`. The PR number is still required.
- `--lane-lint` stays refused in the foreground under background work. So does any other option, such as `--reviewed`.
- A long command inside an exempt call is still judged. `_fg_merge_inner_hit` reads each substitution and backtick part. A nesting too deep to read is refused.
- `_fg_merge_exempt` in `hooks/guard_stream.py` reads the call. `guard_merge` says which segment runs the merge tool. The option names come from `hooks/merge_options.py`.

Cost: no new process and no file written. A call that cannot run long reads nothing. A call that can run long reads the transcript once (unmeasured), by `scan_jobs`, in the guard hook already running. The exemption parses the call's words in that same hook. It starts no process and writes no file. Its cost is unmeasured.

Why: a long foreground wait hides the agents and background commands that are still working. A quick read hides nothing, so it stays.

Why the exemption: a short merge call is the merge tool's own step. Under the rule, a foreground merge under background work was refused. `merge-confirm-repo` records that the auto-mode classifier refuses the background form (measured 2026-11-03 16:56 CST). The exemption removes the first refusal.

Kind: process
Home: hooks/guard_stream.py
Home: hooks/stall_watch.py
Home: hooks/merge_options.py
