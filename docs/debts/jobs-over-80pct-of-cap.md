# Nine CI jobs ran past 80% of their cap

**What.** In the window of 2026-11-05 (then an 80% target of decision `ci-job-caps`, which R3 dropped), nine jobs had a green run past 80% of the cap. checks-windows-guard took 19.7 of 20 min and checks-windows-guard-2 19.9 of 20 (99% each). checks-windows-merge-2, -3, -5 and checks-windows-merge took 90% to 94%. checks-guard took 84%, shell-macos 83% and checks-windows-merge-4 82%. No run ended at a cap, but a slow runner can end the two guard jobs at their cap with no red test.

**Status.** Void. The 80% target is gone: each limit is now the slowest sample x 1.5 (decision `time-limits-end-hangs-only`), so a run near 80% of a computed limit is no defect. Kept, with the nine jobs' figures, until its retire step runs.

**Where.** `.github/workflows/checks.yml`, each job's `timeout-minutes`.

**Decision.** `ci-job-caps`.

**Retire.** Step `ci-recap-jobs` re-caps the nine jobs (decision `ci-job-caps`). Delete this debt after the first green run on main with the new caps, citing that run.
