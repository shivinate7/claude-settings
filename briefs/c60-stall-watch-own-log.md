# c60: the stall watch does not cry wolf on a command that writes to its own log

Cloud build thread brief. Build advisor (2), Oct 26, against claude-settings main e5525a6.
Base: main e5525a6; never rebase onto main after review.

## Incident

Oct 26, merging #586 on the Mac: hooks/stall_watch.py (its --hook wrapper and --watch-pid watcher)
reported merge.py as stalled. merge.py sent its output to a log file, so the watched stdout stayed
quiet past 300 s while the job worked. A guard that cries wolf is spent
(verification-cry-wolf-guard-is-spent).

## Task

1. Before the watcher reports a stall, it also checks whether the job is still writing elsewhere.
   Pick the cheapest reliable signal and say why in the PR: growth of a log file the command
   names by redirection (`> F`, `>> F`, `2>&1 | tee F`, `--log F`), or a declared log
   (an env or description note). Read the act, not a guess (decision predicate-is-the-act).
2. A real stall (no byte on stdout and no growth of any named log for the quiet time) still
   reports exactly as today. Same for the --stop mode: an open job whose named log still grows
   is not listed.
3. Cost: no new process, timer or file; the watcher already polls. State the cost in the
   record (outcomes-mechanize-rules).

## Failure classes and proof

- Test-author first, red on main, in hooks/test_stall_watch.py (and _stop.py if --stop changes):
  a merge.py-like job (quiet stdout, a named log that grows) is not a stall; the same job whose
  log stops growing is a stall; a quiet job with no named log is a stall (bypass check).
- False alarm and bypass both count: a log path in a quoted string or comment is not a
  redirection (building-scanner-respects-strings; use shlex or the guard's own tokenizer).
- It changes a check: a fresh Sonnet reviewer reads the diff; net-value test only after round 3.

## Report

Cap 20 lines: Done, Deviations, Next. Send the green, reviewed head and branch to
"Advise the claude-settings build (2)". No question for shiv: park any in the PR body.
