# Each CI job's cap leaves its slowest run under 80%

## The ruling

Owner, 2026-11-01 18:44 CST: each owner repo raises its job caps generously, as a stopgap, until its time-pinned tests are gone. The owner named the CI fix step that ends the stopgap; it reads as decision `test-strategy-reset` (tests prove outcomes and never fail on runner speed). This repo's caps, with their measured runs, are in the table below.

Owner, 2026-10-27, roadmap step c95 (the cap rule):

- A full CI run is red only when something is broken, never because a job ran out of time.
- The target is a slowest run under 80% of the cap.
- A job that ends at its cap with no red test step is re-capped or split, never left (skill `ci-hygiene`, step 5).
- A cap rises only with a measured figure in the comment beside it. This item is suspended while the stopgap holds, and comes back when roadmap step `time-pinned-tests-go` (time-pinned tests are gone) closes (owner, 2026-11-01 18:44 CST, above).

## The table

Window: each row names its own. A row marked "window of 2026-11-05" or "window of 2026-11-06" uses the window of that name in the first two notes below. An unmarked row uses the newest 30 completed runs of each job in `checks.yml`, from run 39969158671 (2026-10-23) to run 40551443745 (2026-10-27); checks-windows-sweep is projected from that window. Times are minutes from job start to job end.

| Job | Runner | n | Median | Slowest | Cap before | Cap after | Slowest as % of cap after | Cap ends, no red step | Target met |
|---|---|---|---|---|---|---|---|---|---|
| checks (window of 2026-11-05) | ubuntu | 27 | 19.8 | 22.8 | 52 | 52 | 44 | 0 | yes |
| checks-merge-install (split off checks; window of 2026-11-06) | ubuntu | 30 | 17.7 | 21.0 | 60 (provisional) | 30 | 70 | 0 | yes |
| checks-guard (window of 2026-11-06) | ubuntu | 30 | 16.6 | 18.9 | 22 | 27 | 70 | 0 | yes |
| checks-windows-rest (window of 2026-11-06) | windows | 30 | 16.4 | 20.2 | 28 | 28 | 72 | 0 | yes |
| checks-windows-sweep (new; projected) | windows | 30 | 7.3 (projected) | 19.1 (projected: sum of two step maxima) | none | 40 | 49 (19.6 projected) | 0 | yes |
| shell-macos (window of 2026-11-06) | macos | 30 | 21.1 | 23.2 | 28 | 34 | 68 | 0 | yes |
| checks-macos (window of 2026-11-05) | macos | 30 | 19.4 | 30.5 | 55 | 55 | 55 | 0 | yes |
| checks-macos-b (split off checks-macos; window of 2026-11-06) | macos | 30 | 18.5 | 21.5 | 60 (provisional) | 31 | 69 | 0 | yes |
| checks-windows-guard (window of 2026-11-06, off pull_request) | windows | 25 | 16.7 | 19.7 | 20 | 29 | 68 | 0 | yes |
| checks-windows-guard-2 (window of 2026-11-06) | windows | 25 | 17.1 | 19.9 | 20 | 29 | 69 | 0 | yes |
| checks-windows-merge (window of 2026-11-06, off pull_request) | windows | 24 | 11.8 | 13.6 | 15 | 22 | 62 | 0 | yes |
| checks-windows-merge-2 to -5 (window of 2026-11-06) | windows | 23 to 25 | 10.8 to 13.5 | 12.2 to 14.5; at least 15.2 in the cap end | 15 | 22 | 55 to 66; 69 for the cap end | 1, run 42282722326 (checks-windows-merge-2), against the cap in force (15) | yes |
| pointer-windows | windows | 30 | 3.8 | 4.2 | 10 | 10 | 42 | 0 | yes |
| checks-mutate-guard | ubuntu | 30 | 3.7 | 3.9 (old window; see the note below) | 25 | 25 | about 64 (16 projected for batch 7) | 1, run 41786084869, against the cap in force (10) | projected yes |
| checks-windows | windows | 30 | 1.2 | 1.6 | 10 | 10 | 16 | 0 | yes |
| checks-shoot | ubuntu | 30 | 0.8 | 1.0 | 10 | 10 | 10 | 0 | yes |
| scope, ci-done | ubuntu | 30, 19 | 0.1 | 0.1 | 5 | 5 | 3 | 0 | yes |

- Window of 2026-11-05: the rows marked so use the 99 newest completed runs of `checks.yml`, 2026-11-05 17:26 to 2026-11-06 18:00 UTC. 34 of them ran jobs, from run 42074654512 to run 42263498384; the rest skipped every job. The API listing stopped at one page, so runs from 2026-11-03 23:39 (the split) to 2026-11-05 17:26 are not in it. n counts green runs of the job, whatever the run's own end. No run was a re-run and none ended at a cap. Minutes come from `job_minutes` in `merge/merge.py`. Nine jobs were over the 80% target in this window; the window of 2026-11-06 re-capped them. checks-merge-install and checks-macos-b had provisional caps (60) and are re-capped from the same window.
- Window of 2026-11-06: the rows marked so use, per job, the newest 30 green runs in which the job ran a CI step, or fewer where the window ran out. The window is 2026-11-05 12:36 to 2026-11-06 19:54 UTC, runs 42028525645 to 42283749135. A green job whose every CI step was skipped (about 3 s) is no sample. Minutes are job completed_at minus started_at, as `job_minutes` reads them. checks-windows-guard and checks-windows-merge run a slice on pull_request (median 8.0 and 2.2 min), so their rows count only push, schedule and dispatch runs. Each re-capped row's cap is the slowest run, including a run that hit its cap, divided by 0.7, rounded up, so the slowest sits under the merge tool's 70% warning. checks (52), checks-macos (55), checks-windows-sweep (40) and checks-windows-rest (28) were not re-capped here. The shards of one suite share one cap, set from the slowest of its shards: 19.9 min for the Windows guard shards (cap 29), and at least 15.2 min for the Windows merge shards (cap 22). That 15.2 is run 42282722326 (push to main), which ended checks-windows-merge-2 at its 15 min cap inside the git-half suite, with no red test. The window ran under the old caps, so a run near a cap is a floor. No re-capped job's median rose by more than 0.6 min from the older to the newer half of its window; checks-windows-guard fell 4.2 min. The Windows shards grew since 2026-10-27 (guard 582 and 679 s, merge 295 to 520 s, run 40296937814) at the pace of their suites: `hooks/test_guard.py` grew from 16800 to 28421 lines and `merge/test_merge.py` from 577 to 974 tests (main e0f9e2d9 to 5e595822). Debt `windows-shards-outgrow-caps` (the Windows shards grow with their suites) holds the split.
- `checks-mutate-guard`: its 25 min cap is a stopgap. Run 41786084869 ended at the old 10 min cap with 482 of 486 mutants printed KILLED and no red step; the cap-cut step ran 580 s or more. Two slow kills were sped up with no kill lost, so a local run with 4 jobs took 651 s, against 710 s before. Batch 7's lanes add mutants: lane PR 1163 alone measured 946 s locally (+236 s) and lane PR 1157 768 s (+58 s). The sum 710 + 236 + 58 - 59 is 945 s, about 16 min, or 64% of 25 min if CI runs as fast as the local machine. A cap-cut step has no upper bound; the next green run on main replaces the projection. Debt `mutate-guard-split` holds the split.
- `checks-windows-sweep`: the after-figure is projected. The projection subtracts the measured step times of the moved suites from the measured job times; the fixture suite takes 8.2 min slowest and the mutation test 10.9 min slowest (push only). The rows for checks-guard and checks-windows-rest are measured in the window of 2026-11-06. A cap end counts against the cap in force when it ran.
- checks (52) and checks-macos (55) are stopgap caps under the owner's 2026-11-01 18:44 CST ruling above; their slowest runs in the window of 2026-11-05 are 44% and 55% of them. Each step cap carries its own figure in the comment beside it in `checks.yml`.
- The macOS jobs stay at 3 (checks-macos, checks-macos-b, shell-macos): a fourth would queue, as checks-macos waited 379 s in run 41383013723. `merge.deadlineMinutes` in `.github/stamp.json` stays 65, at least the largest cap (55) plus 5.
- Reader: none checks these figures yet. Debt `measured-time-table` (a table of measured times for machine steps) holds the table that will read them from `gh run list`.

## How to measure again

1. List completed runs of `checks.yml` with `gh run list --workflow checks.yml --status completed`, and read each run's jobs with `gh run view <id> --json jobs`. Per job, take the newest 30 green runs in which the job ran a CI step. A job that runs a slice on pull_request counts only its other runs.
2. For each job, take minutes with `job_minutes` in `merge/merge.py` and the cap with `job_caps` in the same file. Do not write a second reader.
3. A cap end is a run whose job minutes reach the cap, whose conclusion is cancelled or failure, and with no failed test step.
4. Per-step times come from the GitHub API job steps (`started_at` and `completed_at`).
5. A run cancelled before its cap by another act, such as a newer push or a batch rebuild, is left out of the sample, and the record names it.
6. A new job takes a provisional cap of 60 min until it has 5 green runs. Keep `merge.deadlineMinutes` in `.github/stamp.json` at least the largest cap plus 5.

Kind: process
Home: .github/workflows/checks.yml
