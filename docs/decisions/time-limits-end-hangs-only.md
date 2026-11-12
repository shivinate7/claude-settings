# A time limit ends a hang and nothing else

## The ruling

Owner, 2026-11-10 14:09 CST: a time limit exists only to end a hung job. His words: "time limits as a rule make little to no sense when they feel arbitrary and are not outcomes related ... I understand keeping time limits at some point for letting hung tests end". The owner accepted this three-part form at 14:10 CST ("yes, that three-part form matches what I meant"):

1. Stop on silence, not total time. A run ends only after it prints nothing for a while.
2. A stop reads "hung", never "failed". A hung check is retried once. If the retry also hangs, the rollup goes red, labelled "hung", and a report names the job (owner, 2026-11-12 11:51 CST, waiting-page item 557, option a).
3. A total-time limit that must stay (CI billing) comes from measured green runs each time. No number is stored in code.

Details, owner 2026-11-10 14:24 CST (answers to triage's four points):

- A check that gives a verdict (lint, tests, Retire) stops on silence, reads "hung" and retries once. Any other background command is only reported and keeps running (decision `stall-watch`).
- Every CI job keeps a total-time limit, computed from recent green runs by a script and generously large. Local tools use the silence stop only.
- `merge.deadlineMinutes` is computed each time from the current CI limits. Reaching it reads "CI still running", never a refusal.
- The silence window of each tool is the longest gap between output lines in its green runs.
- Margins multiply, never add: "+5m is not as generous as like +1.5x".

New jobs, owner 14:36 and 14:37 CST, agreed at 15:03 CST ("yes thats fine agreed"):

- A job is new until its first green run. A new job takes the limit of its nearest job of the same kind (lint, test, mutation, build) times 1.5. With no such job, it takes the largest current limit times 1.5.
- A new job cut at that limit was misjudged ("if it was just made and it then fails in its first run or two that's a sign it was misjudged"). It moves to the largest current limit times 1.5, and the report flags it.

Premises of the script:

- A run the cap cut counts as a sample of at least its limit. A job is cut when it was cancelled, no step failed, and it ran as long as the job's `timeout-minutes` in the workflow today. Without this, a cut run would hide the slowest run and the limit would never rise.
- A failed run, or a run cancelled before its cap by a newer push, is no sample.
- Margins multiply: limit = slowest sample x 1.5, rounded up, at most 360 minutes (GitHub's own ceiling).
- The deadline is the slowest green run's wall clock x 1.5. It is at least the largest job limit, new-job estimates included, and at most 360.

## What exists

`actions/ci-limits/ci_limits.py` reads the newest 30 completed push runs of `checks.yml` on main from the GitHub jobs API. It makes 1 + 30 `gh api` calls in one process, with no timer and no file written. It prints the limits as JSON (`--json`, with `deadlineMinutes`) or as the markdown table of decision `ci-job-caps` (`--table`). When the API cannot be read, every limit is 360 and one warning goes to stderr: a hung job still ends, and a good job is never cut. Its test is `actions/ci-limits/test_ci_limits.py`, run by `checks.yml` with the other opt-in template suites.

## Not built yet

The script only measures. Later steps of the plan (`docs/plans/restart-plan.md`, section 3.2) change what reads it:

- The `timeout-minutes` values in `.github/workflows/checks.yml` still hold stored numbers.
- The merge tool still reads `merge.deadlineMinutes` from `.github/stamp.json`.
- The silence stop, the one retry and the red "hung" rollup of part 2 are not built.
- These local limits keep their raised stopgap values until the silence stop replaces them: `LINT_SECONDS` in `merge/merge.py`, `TIMEOUT` in `lint/check_debt_retire.py` and `lint/check_python_floor.py`, and `timeout` in `hooks/mutate_guard.py` and `janitor/mutate_sweep.py`.

Kind: process
Home: actions/ci-limits/ci_limits.py
