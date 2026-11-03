# Each CI job's cap leaves its slowest run under 80%

## The ruling

Owner, 2026-11-01 18:44 CST: each owner repo raises its job caps generously, as a stopgap, until its time-pinned tests are gone. The owner named the CI fix step that ends the stopgap; it reads as decision `test-strategy-reset` (tests prove outcomes and never fail on runner speed). This repo's caps, with their measured runs, are in the table below.

Owner, 2026-10-27, roadmap step c95 (the cap rule):

- A full CI run is red only when something is broken, never because a job ran out of time.
- The target is a slowest run under 80% of the cap.
- A job that ends at its cap with no red test step is re-capped or split, never left (skill `ci-hygiene`, step 5).
- A cap rises only with a measured figure in the comment beside it. This item is suspended while the stopgap holds, and comes back when roadmap step `time-pinned-tests-go` (time-pinned tests are gone) closes (owner, 2026-11-01 18:44 CST, above).

## The table

Window: the newest 30 completed runs of each job in `checks.yml`, from run 39969158671 (2026-10-23) to run 40551443745 (2026-10-27). Main at the time was 9264397. Times are minutes from job start to job end.

| Job | Runner | n | Median | Slowest | Cap before | Cap after | Slowest as % of cap after | Cap ends, no red step | Target met |
|---|---|---|---|---|---|---|---|---|---|
| checks | ubuntu | 16 | 28.9 | 35.4 | 36 | 52 | 68 | 0 | yes |
| checks-merge-install (new, split off checks) | ubuntu | 0 | none | none | none | 60 (provisional) | about 28 (16.7 projected) | 0 | projected yes |
| checks-guard (new) | ubuntu | 30 | 9.8 | 10.6 | none | 22 | 50 (10.9 projected) | 0 | yes |
| checks-windows-rest | windows | 30 | 17.0 | 43.0 | 38 | 28 | 48 (13.3 projected) | 1, against the cap in force (38) | yes after the split |
| checks-windows-sweep (new) | windows | 30 | 7.3 | 19.1 | none | 40 | 49 (19.6 projected) | 0 | yes |
| shell-macos | macos | 18 | 12.3 | 19.2 | 18 | 28 | 69 | 2, against the cap in force (18) | yes |
| checks-macos | macos | 15 | 31.1 | 37.1 | 50 | 55 | 67 (before the split) | 0 | yes |
| checks-macos-b (new, split off checks-macos) | macos | 0 | none | none | none | 60 (provisional) | about 33 (19.7 projected) | 0 | projected yes |
| checks-windows-guard | windows | 30 | 5.6 | 12.8 | 20 | 20 | 64 | 0 | yes |
| checks-windows-guard-2 | windows | 30 | 11.5 | 13.2 | 20 | 20 | 66 | 0 | yes |
| checks-windows-merge | windows | 30 | 2.0 | 10.7 | 15 | 15 | 71 | 0 | yes |
| checks-windows-merge-2 to -5 | windows | 30 | 8.3 to 9.4 | 9.8 to 10.5 | 15 | 15 | 65 to 70 | 0 | yes |
| pointer-windows | windows | 30 | 3.8 | 4.2 | 10 | 10 | 42 | 0 | yes |
| checks-mutate-guard | ubuntu | 30 | 3.7 | 3.9 | 10 | 10 | 39 | 0 | yes |
| checks-windows | windows | 30 | 1.2 | 1.6 | 10 | 10 | 16 | 0 | yes |
| checks-shoot | ubuntu | 30 | 0.8 | 1.0 | 10 | 10 | 10 | 0 | yes |
| scope, ci-done | ubuntu | 30, 19 | 0.1 | 0.1 | 5 | 5 | 3 | 0 | yes |

- Every after-figure for a new or re-capped job (checks-guard, checks-windows-rest, checks-windows-sweep) is projected. The projection subtracts the measured step times of the moved suites from the measured job times. Cap ends count against the cap in force before this change.
- One full run on the branch (workflow dispatch, run 40559535659, 2026-10-27) measured each job under its new cap: checks 16.9 of 36, checks-guard 7.4 of 22, checks-windows-rest 6.2 of 28, checks-windows-sweep 12.4 of 40, shell-macos 7.6 of 18. The highest was checks-windows-guard-2 at 13.0 of 20 (65%). One run is n=1, so the next 30 runs on main replace the projections.
- `checks-windows-rest`: run 40542065223 (push to main) ended at the 38 min cap that was in force. The job started 16:33:37 UTC, so the cap fired at 17:11:37. GitHub's cancel grace then ran 5 more minutes, to 17:16:37, which is the 43.0 min figure. The step "Record stamp engine fixture suite" (normal slowest 1.5 min, n 28) started at 16:53:15 and never finished. That step now has its own 5 min cap, so a hang reads red at the step.
- `shell-macos`: the 30-run window above does not apply to this row, and neither does the 30-run figure in debt `measured-time-table`. The row uses 18 runs of `checks.yml` from run 41355883918 (2026-11-01 22:11 UTC) to run 41407916830 (2026-11-02 07:41 UTC): 16 green runs and 2 cap ends, range 8.77 to about 19.2 min, median 12.27. Run 41407916830 (PR batch-63e) took 18.07 min in full, not a floor: the job started 07:41:39Z, the steps ran 07:41:40Z to 07:59:40Z, Complete job ended 07:59:42Z, and the cap cancelled the job at 07:59:44Z. Every step was green. Step times in min: checkout-detection 10.80, install_from_main 1.72, ios-ship 1.70 and 1.58, sim-test 1.02 and 1.00. Run 41407758669 (batch-63c, the ready run) is a floor: the job started 07:41:34Z, so the 18 min cap fired at 07:59:34Z, yet the steps ran on. Step times in min: checkout-detection 11.68 (07:41:45 to 07:53:26), install_from_main 1.73, ios-ship 1.70 and 1.85, sim-test (/bin/bash 3.2) 1.02. Then sim-test (bash on PATH) started 07:59:44Z and was cancelled at 08:00:46Z after 1.03 min, which is that step's normal length. The run took about 19.2 min. The sim-test steps grew from 0.05 and 0.03 min in run 41355883918 to about 1.0 min in the newest runs. Runs 41406600962 (batch-63c) and 41375543494 (batch-60), at 11.55 and 13.90 min, were cancelled by other acts, not by the cap, and are left out. The step "install.sh checkout-detection suite" grew (slowest 11.68 min; 10.80 in run 41407916830; mean 6.18 to 7.79 min, oldest against newest six green runs), so it has its own 16 min cap; its slowest is 73% of that cap.
- `checks-macos`: the 30-run window above does not apply to this row. The row uses 20 runs of `checks-macos` from run 41361394638 (2026-11-01 23:17 UTC) to run 41413936732 (2026-11-02 08:33 UTC): 15 green runs, range 25.6 to 37.1 min, median 31.1, no cap ends. The other 5 runs are left out: 3 were cancelled early by a newer run on the same branch (14.1, 21.6 and 11.5 min) and 2 failed (27.3 and 30.1 min). The slowest, run 41413936732 (PR #1075), is 74% of the old 50 min cap, so the 80% target was already met; the merge tool's 70% warning fired. The new 55 min cap is a stopgap under the owner's 2026-11-01 18:44 CST ruling above (37.1 is 67% of it). No step grew by more than 1 min. The step "Guard fixture suite" took 13.0 to 13.5 min on average, 16.62 min at most, 42% of job time, so it has its own 22 min cap (16.62 is 76% of it). The job is split since 2026-11-03: see the split bullet below. The `checks` figures come from the same 20 runs, 41361394638 to 41413936732 (2026-11-01 23:17 to 2026-11-02 08:33 UTC), job minutes. That window is newer than the window of the `checks` row in the table (2026-10-23 to 2026-10-27) and differs from the projected 19.8 min below. Re-measuring `checks` is its own lane. The split keeps the macOS jobs at 3 (with shell-macos): a fourth would queue, as checks-macos waited 379 s in run 41383013723.
- `checks-windows-sweep`: the fixture suite takes 8.2 min slowest and the mutation test 10.9 min slowest (push only).
- `checks`: the 30-run window above and the projected 19.8 min no longer apply to this row. The cause of the gap between the projection and the measured time is unmeasured. The row uses 20 runs of `checks.yml` from run 41361394638 (2026-11-01 23:17 UTC) to run 41413936732 (2026-11-02 08:33 UTC): 16 green runs, range 25.2 to 35.4 min, median 28.9, no cap ends. The other 4 runs are left out: 2 were cancelled by a newer run (13.0 and 11.5 min) and 2 failed (11.8 and 23.7 min). The slowest, run 41407916830, is 98% of the old 36 min cap. The new 52 min cap is a stopgap under the owner's 2026-11-01 18:44 CST ruling above (35.4 is 68% of it, under the merge tool's 70% warning). Step times in min, mean of the oldest 6 green runs to the newest 6, with the maximum: merge tool git-half fixture suite 6.20 to 6.43 (7.22); install.sh checkout-detection suite 3.67 to 5.83 (6.98); stall watch 2.89 (2.92). The checkout-detection suite is the only step that grew by more than 1 min, so it has its own 10 min cap (6.98 is 70% of it). In the newest 6 runs, hooks suites are 36.7% of job time, merge 24.4% and lint 16.6%, so no family dominates. The job is split since 2026-11-03: see the split bullet below.
- Split of 2026-11-03, for wall time. Run 41730427997 was a workflow dispatch on main with the full suite. checks-macos took 40.6 min: it started 8.8 min after the dispatch, in the macOS queue, and ended at +49.5 min. `checks` took 33.4 min. The next slowest job was checks-windows-guard at 19.1 min. The split moves CI steps whole, each with its own `if:`, shell, env and cap. Each suite still runs in one job per event. checks-macos runs the guard suite in 2 shards: `GUARD_SHARD` 1/2 here and 2/2 in the new job checks-macos-b. checks-macos-b also takes the stall watch (282 s), the janitor triggers (265 s) and 3 hooks suites (88 s). The janitor sweep suites stay in checks-macos. The new job checks-merge-install takes the merge suites (388 s), the install suites (492 s) and the janitor triggers (111 s) from `checks`. The times below are projected from the measured CI step times of that run. Each guard shard is taken as half of the 1078 s whole-suite time. That half is unmeasured: the Windows shards measured 582 s and 679 s, 8% apart. checks-macos: 20.9 min on a push and 18.5 min on a pull request, because the janitor sweep mutation test runs off pull_request only. checks-macos-b: 19.7 min. `checks`: 16.9 min. checks-merge-install: 16.7 min. Each new job takes the 60 min provisional cap (How to measure again, item 6). So `merge.deadlineMinutes` in `.github/stamp.json` is 65, the largest cap plus 5. The existing caps stay at 52 and 55 min. The rows above hold the figures from before the split. The first 5 green runs of each new job replace the projections.
- `checks` slowest is 35.4 of 52 (68%), still above half its cap, so debt `checks-job-near-timeout` stays open.

## How to measure again

1. List the newest 30 completed runs of `checks.yml` with `gh run list --workflow checks.yml --status completed`, and read each run's jobs with `gh run view <id> --json jobs`.
2. For each job, take minutes with `job_minutes` in `merge/merge.py` and the cap with `job_caps` in the same file. Do not write a second reader.
3. A cap end is a run whose job minutes reach the cap, whose conclusion is cancelled or failure, and with no failed test step.
4. Per-step times come from the GitHub API job steps (`started_at` and `completed_at`).
5. A run cancelled before its cap by another act, such as a newer push or a batch rebuild, is left out of the sample, and the record names it.
6. A new job takes a provisional cap of 60 min until it has 5 green runs. Keep `merge.deadlineMinutes` in `.github/stamp.json` at least the largest cap plus 5.

Kind: process
Home: .github/workflows/checks.yml
