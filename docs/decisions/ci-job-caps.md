# Each CI job's cap leaves its slowest run under 80%

## The ruling

Owner, 2026-10-27, roadmap step c95: a full CI run must be red only when something is broken, never because a job ran out of time. Each job in `.github/workflows/gates.yml` has a cap of about 2x its slowest run in the last 30 runs. The target is a slowest run under 80% of the cap. A job that ends at its cap with no red test step is re-capped or split, never left (skill `ci-hygiene`, step 5). A cap rises only with a measured figure in the comment beside it.

## The table

Window: the newest 30 completed runs of each job in `gates.yml`, from run 39969158671 (2026-10-23) to run 40551443745 (2026-10-27). Main at the time was 9264397. Times are minutes from job start to job end.

| Job | Runner | n | Median | Slowest | Cap before | Cap after | Slowest as % of cap after | Cap ends, no red step | Target met |
|---|---|---|---|---|---|---|---|---|---|
| gates | ubuntu | 30 | 22.1 | 30.4 | 36 | 36 | 55 (19.8 projected) | 0 | yes after the split |
| gates-guard (new) | ubuntu | 30 | 9.8 | 10.6 | none | 22 | 50 (10.9 projected) | 0 | yes |
| gates-windows-rest | windows | 30 | 17.0 | 43.0 | 38 | 28 | 48 (13.3 projected) | 1, against the cap in force (38) | yes after the split |
| gates-windows-sweep (new) | windows | 30 | 7.3 | 19.1 | none | 40 | 49 (19.6 projected) | 0 | yes |
| shell-macos | macos | 30 | 7.2 | 9.1 | 10 | 18 | 51 | 0 | yes |
| gates-macos | macos | 30 | 26.5 | 32.7 | 50 | 50 | 65 | 0 | yes |
| gates-windows-guard | windows | 30 | 5.6 | 12.8 | 20 | 20 | 64 | 0 | yes |
| gates-windows-guard-2 | windows | 30 | 11.5 | 13.2 | 20 | 20 | 66 | 0 | yes |
| gates-windows-merge | windows | 30 | 2.0 | 10.7 | 15 | 15 | 71 | 0 | yes |
| gates-windows-merge-2 to -5 | windows | 30 | 8.3 to 9.4 | 9.8 to 10.5 | 15 | 15 | 65 to 70 | 0 | yes |
| pointer-windows | windows | 30 | 3.8 | 4.2 | 10 | 10 | 42 | 0 | yes |
| gates-mutate-guard | ubuntu | 30 | 3.7 | 3.9 | 10 | 10 | 39 | 0 | yes |
| gates-windows | windows | 30 | 1.2 | 1.6 | 10 | 10 | 16 | 0 | yes |
| gates-shoot | ubuntu | 30 | 0.8 | 1.0 | 10 | 10 | 10 | 0 | yes |
| scope, ci-done | ubuntu | 30, 19 | 0.1 | 0.1 | 5 | 5 | 3 | 0 | yes |

- Every after-figure for a new or re-capped job (gates, gates-guard, gates-windows-rest, gates-windows-sweep) is projected. The projection subtracts the measured step times of the moved suites from the measured job times. Cap ends count against the cap in force before this change.
- One full run on the branch (workflow dispatch, run 40559535659, 2026-10-27) measured each job under its new cap: gates 16.9 of 36, gates-guard 7.4 of 22, gates-windows-rest 6.2 of 28, gates-windows-sweep 12.4 of 40, shell-macos 7.6 of 18. The highest was gates-windows-guard-2 at 13.0 of 20 (65%). One run is n=1, so the next 30 runs on main replace the projections.
- `gates-windows-rest`: run 40542065223 (push to main) ended at the 38 min cap that was in force. The job started 16:33:37 UTC, so the cap fired at 17:11:37. GitHub's cancel grace then ran 5 more minutes, to 17:16:37, which is the 43.0 min figure. The step "Record stamp engine fixture suite" (normal slowest 1.5 min, n 28) started at 16:53:15 and never finished. That step now has its own 5 min cap, so a hang reads red at the step.
- `gates-windows-sweep`: the fixture suite takes 8.2 min slowest and the mutation test 10.9 min slowest (push only).
- `gates` was not re-capped: 2x its new slowest (19.8) is above 36, and a raise has no measured reason.
- `gates` slowest is still above half its cap, so debt `gates-job-near-timeout` stays open.

## How to measure again

1. List the newest 30 completed runs of `gates.yml` with `gh run list --workflow gates.yml --status completed`, and read each run's jobs with `gh run view <id> --json jobs`.
2. For each job, take minutes with `job_minutes` in `merge/merge.py` and the cap with `job_caps` in the same file. Do not write a second reader.
3. A cap end is a run whose job minutes reach the cap, whose conclusion is cancelled or failure, and with no failed test step.
4. Per-step times come from the GitHub API job steps (`started_at` and `completed_at`).
5. A new job takes a provisional cap of 60 min until it has 5 green runs. Keep `merge.deadlineMinutes` in `.github/stamp.json` at least the largest cap plus 5.

Kind: process
Home: .github/workflows/gates.yml
