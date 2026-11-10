# The mutation test cannot kill the push-batch-held mutants that need the merge tool

- **What.** The mutant copy of the repo has no `merge/` folder, so the gh half of rule `push-batch-held` always reads as unread there. Only the unread-log mutant can die. Other mutants survive: the deny wiring, the draft filter, the base filter, the own-branch filter, the moves-nothing branch and the merged-tip skip. The cause is that the test controls for those judge the allow alone.
- **Where.** `hooks/mutate_guard.py` (the mutant root and the `push-batch-held` row) and `hooks/guard_merge.py`, `batch_held_hit`.
- **Decision.** `batch-freeze-lane-set`, the frozen lane set.
- **Retire.** The mutant root holds a copy of `merge/`, or a log-based case kills each of those mutants, and the mutation run shows no survivor on `batch_held_hit`. `hooks/test_mutate_ci.py` passes.
