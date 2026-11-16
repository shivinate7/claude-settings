---
id: pending
slug: fg-bash-while-bg
---

# A long foreground command waits in the background while the session's agents and background commands run

## The ruling

Owner, 2026-11-16 13:47 CST: "refuse only commands that can run long, such as tests, lint, merges, builds and installs, or anything asking a time limit over 60 s. Quick reads stay in the foreground."

Mistake: a session ran a long command in the foreground while its agents and background commands ran. The call held the session still. No notice from that work could be read until the call ended.

- The guard rule `fg-bash-while-bg` in `hooks/guard_stream.py` refuses a Bash or PowerShell call that is in the foreground, can run long, and is made while this session has background work.
- Refusal text: "refused in the foreground while background work runs"; rerun it with `run_in_background` and it is allowed.
- Background work is a background command or a background agent with no terminal task notice and no TaskStop result. `scan_jobs` in `hooks/stall_watch.py` reads it from the transcript. It is the one reader of that state.
- A call can run long when one command in it is a test run (pytest, unittest, jest, vitest, a `test_*` script), a lint, a `merge` run, a build (make, xcodebuild, cargo, go, gradle, a package script named build), an install (pip, npm, brew, apt), or a `verdict` run. A `timeout` over 60000 ms counts too, even on a quick read. The roster is `FG_PROGRAMS` and its neighbours in `hooks/guard_stream.py`.
- A call is read by command word and shape, never by substring. `git status`, `cat`, `grep` and `ls` stay in the foreground.
- A call that sets `run_in_background`, a call from an agent, and a call made when the transcript is missing or unreadable all pass. A missing transcript fails open, as the question box does.
- The rule judges the PowerShell tool the same as Bash.
- Order: it runs before `check-timeout` (`background-check-through-verdict`). A foreground `merge --lane-lint` under background work gets this refusal. Its rerun in the background then meets `check-timeout`'s limit. With no background work, `check-timeout` is unchanged.

Cost: no new process and no file written. A call that cannot run long reads nothing. A call that can run long reads the transcript once, by `scan_jobs`, in the guard hook already running.

Why: a long foreground wait hides the agents and background commands that are still working. A quick read hides nothing, so it stays.

Kind: process
Home: hooks/guard_stream.py
Home: hooks/stall_watch.py
