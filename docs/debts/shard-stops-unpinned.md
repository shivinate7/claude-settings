# Shard stops have no test

**What.** Three `raise Stop` in the mutation test run have no test that reaches them. They are a shard in two jobs, shard counts that differ or fall outside 1 to M, and a `MUTATE_SHARD` env that does not match its step. A mutant that turned all three into no-ops left the 7 shard cases and the one-job cases green. They fire only on a hand-edited checks.yml. A regression in them goes unseen.

**Where.** `mutate_run_check` in `merge/merge.py`: the shard-in-two-jobs stop, the shard-count stop, and the `MUTATE_SHARD` stop in the plan step.

**Decision.** lanes-run-no-full-ci-job (a lane runs no full CI job, and the lint runs the mutation test shards on a touched head).

**Retire.** Closed by a test-author who pins each of the three stops with a case in `merge/test_lane_lint.py`. Each case goes red on a mutant that removes its stop.
