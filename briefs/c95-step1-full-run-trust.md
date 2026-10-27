# Brief: c95 step 1a, the full run stops timing out

Repo: shivinate7/claude-settings, from current main. One lane: builder (sonnet), then reviewer (sonnet). Ruling: shiv, Oct 27 12:07 CDT, waiting page item 31, pick (e) "trust first, then cut in steps" (roadmap step c95 holds the reading).

## Task
Step 1 needs a full run where red means broken, not out of time.
1. Measure: for each job in .github/workflows/gates.yml, its duration over the last 30 completed runs (GitHub API, actions/runs and their jobs), and how many ended at their timeout with no red test step. Write the table into the decision that owns job caps (find it: the caps step c39 landed one), with a gold-standard column (target: the slowest of 30 runs under 80% of its cap).
2. Fix each job over that target: split its slowest suite into another job, or raise the cap from the measured numbers (rule: a job that ends at its cap with no red step is re-capped or split). merge.py already prints "job X: N of M min" warnings; reuse its numbers, do not add a second reader.
3. A small script (or a mode of an existing one) that counts merges to main that a later commit had to repair: a revert, or a commit whose message names a fix for a batch. Print the count for the last 14 days. It is read on demand, never on a timer.

## Failure classes
- A cap raised with no measured reason.
- A split that drops a suite from every job (a test that no longer runs anywhere).

## Check that proves it done
The table, the counts, and a test for the counting script (red on main: no script; green: it counts a planted revert in a fixture repo). `python3 bin/ci-job gates --lint --base origin/main` and `bin/ste-changed origin/main` pass. The branch's own CI run shows no job past 80% of its cap, or the report names the one that is and why.

## Report
At most 15 lines: PR (draft), head, the table's worst three jobs before and after, the repaired-merge count, review verdict. Send the green, reviewed head to the build advisor thread "Advise the claude-settings build (9)". Do not rebase onto main and do not merge.
