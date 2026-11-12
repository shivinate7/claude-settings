# Each CI job's time limit comes from its green runs

## The ruling

Owner, 2026-10-27, roadmap step c95 (the cap rule): a full CI run is red only when something is broken, never because a job ran out of time.

Owner, 2026-11-10 12:11 CST, to triage: "i thought i'd already established to coordinator that all time related tests need to be deprecating (that's prob alrdy recorded) but also to generously raise time limits in the interim so that tests dont fail off time".

Owner, 2026-11-10 14:09 CST: a time limit stays only to end a hung job. Decision `time-limits-end-hangs-only` holds the rule: each CI job's limit is the slowest sample from the newest 30 green runs on main, times 1.5, never plus a fixed number. `actions/ci-limits/ci_limits.py` computes it.

- A job that ends at its cap with no red step is a sample of at least its cap, so its limit rises.
- A job with no green run yet is new. It takes the limit of its nearest kind times 1.5, else the largest times 1.5. If it is cut at that limit, it was misjudged and takes the largest times 1.5.
- The `timeout-minutes` in `.github/workflows/checks.yml` still hold stored numbers. A later step makes them read the script.
- `merge.deadlineMinutes` is the slowest green run's wall clock times 1.5, at least the largest job limit.
- The local tool limits (`LINT_SECONDS` in `merge/merge.py`, `TIMEOUT` in `lint/check_debt_retire.py` and `lint/check_python_floor.py`, and `timeout` in `hooks/mutate_guard.py` and `janitor/mutate_sweep.py`) stay raised until the silence stop of decision `time-limits-end-hangs-only` replaces them. Any other local time limit rises when it fails off time.
- The raised caps and local limits end with roadmap step `time-pinned-tests-go` (time-pinned tests are gone), and with the silence stop.

## The table

`python3 actions/ci-limits/ci_limits.py --table` prints it. This copy was read at 12:07 CST on 2026-11-12 from the newest 30 completed push runs of `checks.yml` on main (run 42544938082, 2026-11-09, to run 43244808204). Limits are minutes. No job was cut at its estimate while new.

| Job | Limit (minutes) | Note |
| --- | --- | --- |
| all-jobs-passed | 89 |  |
| checks | 59 |  |
| checks-guard | 38 |  |
| checks-guard-2 | 27 |  |
| checks-macos | 59 |  |
| checks-macos-b | 47 |  |
| checks-merge-install | 47 |  |
| checks-mutate-guard | 55 |  |
| checks-shoot | 12 |  |
| checks-waiting-page | 11 |  |
| checks-windows | 5 |  |
| checks-windows-guard | 37 |  |
| checks-windows-guard-2 | 40 |  |
| checks-windows-guard-3 | 36 |  |
| checks-windows-merge | 32 |  |
| checks-windows-merge-2 | 32 |  |
| checks-windows-merge-3 | 33 |  |
| checks-windows-merge-4 | 32 |  |
| checks-windows-merge-5 | 28 |  |
| checks-windows-rest | 48 |  |
| checks-windows-sweep | 25 |  |
| ci-done | 89 |  |
| mutation-report | 1 |  |
| pointer-windows | 10 |  |
| scope | 1 |  |
| shell-macos | 49 |  |
| deadlineMinutes | 360 | the merge deadline |

- A step's limit is in the JSON (`--json`), keyed `job/step`, from the same rules.
- `all-jobs-passed` and `ci-done` wait on the other jobs, so their limits follow the slowest job.
- `deadlineMinutes` is at the 360 clamp: one green run in the window had a wall clock of 277 minutes (run 42547961769).
- The jobs of `lane-touched-tests.yml` (draft runs only) are outside the table. Its `run` jobs keep a provisional 10 minute cap and `touched` keeps 5.
- The macOS jobs stay at 3 (`checks-macos`, `checks-macos-b`, `shell-macos`): a fourth would queue.
- Debts `windows-shards-outgrow-caps` and `mutate-guard-split` hold the splits of the Windows guard shards and of `checks-mutate-guard`.

## How to measure again

1. Run `python3 actions/ci-limits/ci_limits.py --table` from a checkout of this repo, with `gh` signed in. It reads the jobs API, with 31 calls in one process.
2. Minutes come from `job_minutes` in `merge/merge.py`, and the caps from `job_caps` in the same file. The script calls both. Do not write a second reader.
3. A cut run is cancelled, has no failed step, and ran at least as long as its cap in force. A run cancelled earlier by a newer push or a batch rebuild is no sample.
4. When the API cannot be read, every limit is 360 and the script warns on stderr.

Kind: process
Home: .github/workflows/checks.yml
