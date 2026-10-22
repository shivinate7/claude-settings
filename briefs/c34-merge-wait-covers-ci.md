# c34. The merge tool waits for CI to finish, not for a fixed 30 minutes

Checked claude-settings main at 987f682 and batch branch batch-oct22c (#562).

Cause: .github/stamp.json sets merge.deadlineMinutes to 30 (merge/merge.py MERGE_DEFAULTS is 45).
The CI jobs' own caps in .github/workflows/gates.yml are longer: one job has timeout-minutes 36
on main, and #562 raises the macOS job to 50. So a green but slow run outlasts the wait, as on
#562 on Oct 22. actions/stamp/README.md already says to set deadlineMinutes "to a bit more than
your slowest required check"; nothing checks that it is.

Brief, claude-settings (after #562 merges, or as a lane in the next batch):
1. Set merge.deadlineMinutes in .github/stamp.json to the largest timeout-minutes of a job in
   .github/workflows plus 5 (55 once #562 is on main).
2. Add one check, in the home that already validates stamp.json (find it; extend it, do not add a
   second): it fails when deadlineMinutes is below the largest job timeout-minutes in the
   workflows. Test: red on main (30 below 36), green after step 1.
3. The report-gate timing test that failed once in a full run and passed alone: run it 20 times on
   main. If it fails, fix the cause (the time it reads, or what it races), never add a retry or
   a longer sleep. If it never fails, say so and change nothing.
Report: the files changed, the test red then green, and the 20-run count.
