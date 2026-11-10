# A time limit ends only a hung run

## The ruling

Owner, 2026-11-10 14:09 CST, typed in the retrospective session. The coordinator relayed it at 14:10 and 14:12 CST. At 14:10 CST he confirmed the three parts below: "yes, that three-part form matches what I meant".

His reason, in his words: "time limits as a rule make little to no sense when they feel arbitrary and are not outcomes related." A fixed limit breaks when the code grows. He keeps a time limit "for letting hung tests end". He does not accept the current use of time limits as an outcome-based approach.

1. **Stop on silence, not total time.** A run ends only after it prints nothing for a set window. A slow run that keeps printing is never cut.
2. **A stop reads "hung", never "failed".** The report reads "stopped, no output for N min". A stop is never red and never refuses a merge. Retry the run once. Then report it to the owner.
3. **Where a total-time limit must stay, read it. Never store it.** CI's billing limit is one example. Read it from recent green runs each time. Never store it as a number in code.

## Open

- The silence window N comes from a measurement. That measurement is not made yet, so N is unmeasured. No value is set here.
- The ruling does not say which CI job caps stay as total-time limits, and which only end a hung run. The stored caps stay until the owner rules.
- The watcher in `hooks/stall_watch.py` prints a report after 300 quiet seconds, and never stops a job. Decision `stall-watch` (a stalled background command is reported, never stopped) holds that. Part 1 stops a silent run. The two conflict. This ruling does not change `stall-watch`.
- `merge.deadlineMinutes` (65, in `.github/stamp.json`) is not named here. It stays until the owner rules.

## Replaces (not built)

The code still holds these limits. Each one leaves the code when its change is built, under part 1 or part 3.

- `merge/merge.py`: `LINT_SECONDS = 1200`.
- `lint/check_debt_retire.py`: `TIMEOUT = 600`.
- `hooks/mutate_guard.py`: one 1200 s `timeout=` in a subprocess call.
- `janitor/mutate_sweep.py`: one 1200 s `timeout=` in a subprocess call.
- `lint/check_python_floor.py`: `TIMEOUT = 300`.
- The CI job caps and step caps in decision `ci-job-caps` (CI job caps). Their stored values stay until the reader is built.

Kind: process
Home: merge/merge.py
