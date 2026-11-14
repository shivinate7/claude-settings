# A shard test asserts the order that parallel mutants run in

- **What.** `ShardTests.test_no_shard_runs_all` compares the list of mutants `run_one` saw with the entry order. `run_mutants` runs them in a thread pool, so under load the order can differ. A lane lint on 2026-11-13 failed once with `['a', 'c', 'b']` against `['a', 'b', 'c']`. The test passed three of three reruns on an idle machine. The harm: a red lint that a rerun clears.
- **Where.** `hooks/test_mutate_shared.py`, `ShardTests.test_no_shard_runs_all`, and the thread pool in `hooks/mutate_shared.py`, `run_mutants`.
- **Decision.** `none`.
- **Retire.** The test compares the sorted list, and `hooks/test_mutate_shared.py` passes.
