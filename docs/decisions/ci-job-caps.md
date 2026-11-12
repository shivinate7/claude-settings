# Each CI job's time limit comes from its green runs

## The ruling

A full CI run is red only when something is broken, never because a job ran out of time (owner, 2026-10-27, roadmap step c95). A job's time limit exists to end a hang, so it is generous and computed: decision `time-limits-end-hangs-only` holds the rule, and `actions/ci-limits/ci_limits.py` computes it. R3 of the restart plan replaced the 80% target, the re-cap-or-split item and the measured-figure comment of step c95.

- A job's limit is the slowest sample of the newest 30 completed push runs on main, times 1.5, never plus a fixed number.
- By default a job that ends at its cap with no failed CI step is a sample of at least its cap, so its limit rises. The owner's answer is pending (waiting-page item 586); `--green-only` ignores a cut run.
- A job with no green run yet is new. It takes the limit of its nearest kind times 1.5, else the largest times 1.5. If it is cut at that limit, it was misjudged and takes the largest times 1.5.
- Every job limit is at least the median of all job limits, derived each run (coordinator, 2026-11-12 12:22 CST), so a job that runs for seconds is never cut at a minute.
- A job skipped in every run of the window never ran on main. It shows "not measured on main", in the table and as null in the JSON, and it joins no median, estimate or deadline.
- The caps the script compares a cut run against are the `timeout-minutes` of `checks.yml` on the base ref (`origin/main`), never the checkout.
- `merge.deadlineMinutes` is the slowest green run's wall clock times 1.5, at least the largest job limit.
- The `timeout-minutes` in `.github/workflows/checks.yml` still hold stored numbers, raised generously as a stopgap until time-pinned tests are gone (owner, 2026-11-01 18:44 CST, decision `test-strategy-reset`). A later step makes them read the script.
- The local tool limits (`LINT_SECONDS` in `merge/merge.py`, `TIMEOUT` in `lint/check_debt_retire.py` and `lint/check_python_floor.py`, and `timeout` in `hooks/mutate_guard.py` and `janitor/mutate_sweep.py`) stay raised (owner, 2026-11-10 12:11 CST) until the silence stop replaces them. Any other local time limit rises when it fails off time.
- The raised caps and local limits end with roadmap step `time-pinned-tests-go` (time-pinned tests are gone), and with the silence stop.

## The table

`python3 actions/ci-limits/ci_limits.py --table` prints it. This copy was read at 12:25 CST on 2026-11-12 from the newest 30 completed push runs of `checks.yml` on main (run 42544938082, 2026-11-09, to run 43244808204), with the caps of `origin/main`. Limits are minutes. The median floor is 33. No job was cut at its estimate while new.

| Job | Limit (minutes) | Note |
| --- | --- | --- |
| all-jobs-passed | not measured on main |  |
| checks | 59 |  |
| checks-guard | 38 |  |
| checks-guard-2 | 33 |  |
| checks-macos | 59 |  |
| checks-macos-b | 47 |  |
| checks-merge-install | 47 |  |
| checks-mutate-guard | 55 |  |
| checks-shoot | 33 |  |
| checks-waiting-page | 33 |  |
| checks-windows | 33 |  |
| checks-windows-guard | 37 |  |
| checks-windows-guard-2 | 40 |  |
| checks-windows-guard-3 | 36 |  |
| checks-windows-merge | 33 |  |
| checks-windows-merge-2 | 33 |  |
| checks-windows-merge-3 | 33 |  |
| checks-windows-merge-4 | 33 |  |
| checks-windows-merge-5 | 33 |  |
| checks-windows-rest | 48 |  |
| checks-windows-sweep | 33 |  |
| ci-done | not measured on main |  |
| mutation-report | 33 |  |
| pointer-windows | 33 |  |
| scope | 33 |  |
| shell-macos | 49 |  |
| deadlineMinutes | 360 | the merge deadline |

- A CI step's limit is in the JSON (`--json`), keyed `job/CI step`, from the same rules.
- `all-jobs-passed` and `ci-done` were skipped in every run of the window, so the script has no measure for them.
- `deadlineMinutes` is at the 360 clamp. One green attempt, run 42547961769 attempt 1, ran 4 hours 37 minutes from its first job start to its last job end, though no job of it ran past its limit. The cause of the gap is unmeasured.
- The jobs of `lane-touched-tests.yml` (draft runs only) are outside the table. Its `run` jobs keep a provisional 10 minute cap and `touched` keeps 5.
- The macOS jobs stay at 3 (`checks-macos`, `checks-macos-b`, `shell-macos`): a fourth would queue.
- Debts `windows-shards-outgrow-caps` and `mutate-guard-split` hold the splits of the Windows guard shards and of `checks-mutate-guard`.

## How to measure again

1. Run `python3 actions/ci-limits/ci_limits.py --table` from a checkout of this repo, with `gh` signed in. It reads the jobs API: one call for the run list and one per run, in one process.
2. Minutes come from `job_minutes` in `merge/merge.py`, and the caps from `job_caps` in the same file. The script calls both. Do not write a second reader.
3. A cut run is cancelled, has no failed CI step, and ran at least as long as the job's `timeout-minutes` on the base ref. A run cancelled earlier by a newer push or a batch rebuild is no sample.
4. When the API cannot be read, every limit is 360 and the script warns on stderr.

Kind: process
Home: .github/workflows/checks.yml
