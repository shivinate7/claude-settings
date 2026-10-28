# c95 step 2: its bar and its step-back rule (plan, no code)

Step c95, "CI at milestones": step 2 is q_max's shape, quick checks per branch and the full suite on main only. Ruling: shiv, Oct 27 12:07 CDT, item 31, pick (e). No record named step 1's bar (checked Oct 28). This plan proposes one.

## Counts, main since batch #725 (step 1 landed, merged 00:23 CDT Oct 28)

Read 02:10 CDT Oct 28 with `gh api repos/.../actions/runs` (workflow `gates`) and `python3 merge/repaired_merges.py`.

| Full run on main | Head | Result | Slowest job vs cap |
|---|---|---|---|
| #725 batch-oct28a | 0fb91de | green, attempt 1 | gates-macos 39.3 of 50 min (79%) |
| #737 batch-oct28c | b09aece | green, attempt 1 | gates-macos 26.2 of 50 (52%) |
| #741 batch-oct28d | 3bebbd3 | running at read time | unknown |

- Green: 2 of 2 completed. Timed out: 0. Re-run to repair: 0 (every run is attempt 1).
- Repaired merges (repaired_merges.py, a floor): 0 in 1 day, 0 in 14 days.
- Batch PR runs: oct28c and oct28d green; oct28b red on real tests (silent-undo check; Windows stamp fixture, step c158), not a timeout. The lane was fixed and joined oct28c. No red reached main.
- Baseline before #725, last 60 push runs on main: 17 green, 10 red, 33 cancelled.
- gates-macos at 79% of its cap on the #725 run is one point under 1a's 80% target. Watch it.

A sample of 2 proves nothing yet. Step 1's bar is not met under any option below.

## Step 2's bar: options

Window: the last N completed full runs on main. A run cancelled by a newer push is not counted.

| Option | Bar | Gains | Loses |
|---|---|---|---|
| A. Clean streak | 10 in a row green, 0 at cap, 0 repaired | Highest trust before cutting CI | One flake resets the count; at ~3 batches a night, 4+ days, likely longer |
| B. Share, root-caused (pick) | At least 9 of last 10 green; 0 ended at cap with no red step; 0 repaired merges; each red has a named cause, never "flake" | Tolerates one red with a cause; reachable in ~3-4 days | One real red can pass inside the window |
| C. Days | 7 days, every main run green | Simple to read | Idle days count as trust; measures calendar, not runs |
| D. Short | 5 of 5 green | Step 2 starts in ~2 days, saves minutes soonest | 5 runs cannot separate 90% from 70% green |

## Step-back rule: options

Read on demand at each batch merge report, with the four pace numbers. No timer, no new log. Cost: one `actions/runs` read and one repaired_merges.py run per batch merge.

| Option | Steps back to step 1 when | Gains | Loses |
|---|---|---|---|
| 1. Any repaired merge (pick) | One merge that passed branch quick checks needs a later fix on main; or green share in the last 10 falls under 8; or a job ends at cap with no red step | Catches the one risk step 2 adds: a defect the quick checks miss | One unlucky merge undoes the step |
| 2. Two strikes | Two repaired merges in 10 runs, or share under 7 of 10 | Fewer flip-flops | Main can stay broken across two batches |
| 3. Share only | Green share under 8 of 10 | Simplest | Blind to defects that a re-run hides |

After a step back, the step-2 bar starts from a fresh window of 10.

## Pick: B with step-back 1

- B's bar is a measured share, and the "named cause" clause blocks a "flake" excuse (drive-to-green rule).
- Step-back 1 watches exactly what step 2 gives up: the full suite on each branch.
- The same bar, one step later, gates step 3 (milestone runs), with "main run" read as "milestone run".

## Home and next

- Step-1 bar and step-2 rule belong in c95's record (`note`), and its rule text in the decision that owns job caps. The orchestrator writes both after shiv rules.
- Deferred: why — the bar is shiv's to set (a recorded ruling governs the cut). Question: B+1 (recommended), A, C, or D?
- Until then: keep counting. Re-read this table at each batch merge.
