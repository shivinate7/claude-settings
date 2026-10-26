# c61: main's push run goes fully green; the Windows guard and merge jobs fit their caps

Cloud build thread brief. Build advisor (2), Oct 26, against claude-settings main e5525a6.
Base: main e5525a6; never rebase onto main after review. Push roadmap edits to the branch only;
only "Triage the roadmap (2)" republishes the roadmap page.

## Finding

On push, schedule and dispatch runs, harness-scope.sh turns every suite on. There
gates-windows-guard (timeout-minutes 15) and gates-windows-merge (20) end "cancelled" at their
caps: main e5525a6's push run, and dispatch runs on the d6 and c47 lanes. On PR runs, scoped to
the diff, both pass. So main is never fully green, and a red job at its cap reads as noise.
Batch rule: a job that ends at its cap is re-capped or split, never a reason to drop a lane.

## Task

1. Measure first, no code change: from the GitHub Actions API, read each step's duration for both
   jobs on the last 5 push or dispatch runs that ran the full suite, and on 5 green PR runs.
   Name the step that eats the time. Report the numbers in the PR body.
2. Then pick the cheaper fix and say why: raise the cap to about 1.5x the measured full-suite
   time, or split the long suite into a second job (matrix or shard) so each fits. A split keeps
   every case running; never drop, skip or narrow a case to fit.
3. If a suite is slow from a defect (a sleep, a retry loop, a hung child), fix that cause instead
   and name it.

## Failure classes and proof

- Proof: a dispatch run of gates.yml on the branch where both jobs end green with full scope.
- False green: the job must still run the same case count as before; print and compare it.
- A gate's verdict may change: a fresh Sonnet reviewer reads the diff.

## Report

Cap 15 lines: Done, Deviations, Next. Send the green, reviewed head and branch to
"Advise the claude-settings build (2)". No question for shiv: park any in the PR body.
