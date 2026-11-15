# The merge tool prints a timed line at the start and end of each phase

## The ruling

Coordinator, 2026-11-14 06:51 CST, folded from step `merge-tool-phase-timing`: one merge run shows where its time goes. The merge tool prints `merge: phase <name>: start` and `merge: phase <name>: done in <N> s` around each phase of `merge --confirm`. A phase that raises prints `stopped after <N> s` and the error goes on.

The phases, in order: `lock` (taking the base's merge lock), `main-run` (reading the base's newest run), the silent-undo scan (it prints its own start and done lines), `debt-check`, `head-checks` (reading the head's checks), `prove` (the fresh read of the base before the merge), `merge-call` (the merge request).

Why: run `merge 3377 --confirm` ran 28 min 35 s with no progress line after a 2 s scan, and the last 11 min of the wait are unmeasured. The merge call on #3399 took 21 s. Two merges are not enough to redesign anything.

Measure over 5 merges before any redesign. This record changes no wait, no order and no verdict. A redesign of a slow phase is a new record, with its numbers.

Cost: at most two timed lines a phase and at most 12 for a run that reaches the merge call. It starts no thread or process and writes no file. The fixture suite for this record (`merge/test_merge_phase_timing.py`) pins the line count, the thread starts and the file count. A timing line that cannot be written (a closed pipe, as in `merge N --confirm | head -1`) is dropped, so it never stops a phase or leaves the lock held; the same suite pins that.

Measured so far: two merges, in the reason above. Unmeasured: how long each other phase takes.

Kind: process
Home: merge/merge.py
