# A time limit ends only a hung run

## The ruling

Owner, 2026-11-10 14:09-14:10 CST, typed in the retrospective session. The coordinator relayed it at 14:12 CST. He confirmed the three parts below at 14:10 CST: "yes, that three-part form matches what I meant".

His reason, in his words: "time limits as a rule make little to no sense when they feel arbitrary and are not outcomes related." A fixed limit breaks when the code grows. He keeps a time limit "for letting hung tests end". He does not accept the current use of time limits as an outcome-based approach.

1. **Stop on silence, not total time.** A run ends when it prints nothing for a set window. The silence rule never cuts a slow run that keeps printing. The one exception is a total-time limit kept under part 3, read from green runs.
2. **A stop reads "stopped, no output for N min", never "failed".** A stop means that the run hung. A stop is never red and never refuses a merge. Retry the run once. Then report it to the owner.
3. **Where a total-time limit must stay, read it. Never store it.** It is the one exception to part 1. Read it from recent green runs each time. Never stored as a number.

## Owner's answers, 2026-11-10 14:24 CST

Owner, 14:24 CST, typed in the retrospective session. The coordinator relayed it at 14:24 CST. He answered four open points:

4. **Verdict checks stop on silence.** Owner: "yes that's ok". <!-- ste-disable-line STE008 owner's words, quoted --> A check that gives a verdict (lint, tests, the Retire check) stops on silence, is retried once, and reports "stopped, no output for N min". Any other background command is only reported and keeps running. Decision `stall-watch` (a stalled background command is reported; a verdict check is to stop on silence) holds that split.
5. **Every CI job keeps a total-time limit.** Owner: "that's fine too but it should be generously large maybe". <!-- ste-disable-line STE008 owner's words, quoted --> GitHub needs one. A script computes each CI job's limit from recent green runs. No one edits it by hand. Each limit is generously large ("generously large maybe"). Local tools use only the silence stop: lane lint, the Retire check, mutation runs and the Python floor check.
6. **`merge.deadlineMinutes` is a moving target.** Owner: "this needs to be a moving target". A script computes it each time from the current CI job limits. It is never stored. When a run reaches it, the report reads "CI still running", never a refusal.
7. **The silence window is measured per tool.** Owner: "that's fine too as long as its generous though like +5m is not as generous as like +1.5x etc". <!-- ste-disable-line STE008 owner's words, quoted --> The window is the longest gap between output lines in green runs, measured per tool. The measure reads `verdict` logs locally and timestamped job logs in CI.

General rule, from the same answer: a margin multiplies the measured value, for example 1.5 times. It never adds a fixed amount. The multiplier's value is not set here.

## Not built

Nothing here is built. Each item is code, a value or a script.

- The silence stop in each local tool. Each leaves the code for it: `merge/merge.py` `LINT_SECONDS = 3600` (the lint run and `ci_job_run`; was 1200, the interim raise in pull request 2557), `lint/check_debt_retire.py` `TIMEOUT = 1800` (was 600, the interim raise in pull request 2557), `hooks/mutate_guard.py` and `janitor/mutate_sweep.py` (one 3600 s `timeout=` each; was 1200 s, the interim raise in pull request 2557), `lint/check_python_floor.py` `TIMEOUT = 900` (was 300, the interim raise in pull request 2557).
- The silence stop for verdict checks in `hooks/stall_watch.py`. It never stops a job today.
- The silence window per tool, and the multiplier. Neither value is set. The window N is unmeasured.
- The CI job limits, computed by a script from recent green runs. Their stored values stay in force until the reader is built (decision `ci-job-caps`).
- The limit of a new CI job: 1.5 times its nearest similar job's computed limit. A new job that hits its limit in its first one or two runs moves to 1.5 times the largest current job's computed limit (decision `ci-job-caps`, New jobs section).
- `merge.deadlineMinutes` (80 today, stored in `.github/stamp.json`; was 65, the interim raise in pull request 2557). The rule: computed from the current CI job limits, never stored. The stored 80 stays until the reader is built.

Kind: process
Home: merge/merge.py
