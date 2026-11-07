# Nine CI jobs run past 80% of their cap

**What.** In the window of 2026-11-05 (decision `ci-job-caps`, each job's cap leaves its slowest run under 80%), nine jobs had a green run past 80% of the cap. The re-cap of 2026-11-07 raised each cap, and the slowest green run of each is now 66% to 75% of its new cap (checks-guard 18.2 of 25, shell-macos 23.9 of 32, checks-windows-guard 19.7 of 27, checks-windows-merge, -3 and -4 at 14.5, 14.6 and 14.8 of 22). Two figures are lower bounds, not slowest runs. checks-windows-guard-2 had 6 cap ends at 20 min, so its 30 min cap holds at least 67%. checks-windows-merge-2 and -5 had 3 cap ends at 15 min, so their 22 min caps hold at least 69%. The new caps are a bandaid for time-pinned tests; the cause fix is roadmap step `time-pinned-tests-go`.

**Where.** `.github/workflows/checks.yml`, each job's `timeout-minutes`.

**Decision.** `ci-job-caps`.

**Retire.** Each of the nine jobs has its slowest green run under 80% of its new cap over at least 5 green runs after the re-cap, with no cap end. Read it as in "How to measure again" in decision `ci-job-caps`. Then delete this debt.
