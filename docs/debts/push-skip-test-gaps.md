# Three gaps remain in the push-skip tests

- **What.** Three gaps remain in the push-skip tests, found in pull request 3282 round 1: the `full_run` key in `read_heads` is a stale name for "the run passed"; the test `test_a_full_run_whose_only_skipped_steps_are_mutation_report_steps_skips` no longer proves an exemption, since no skipped step stops the skip; and the batch case beside a narrowed lane case cannot tell the batch path from the lane path.
- **Where.** `actions/push-skip/push-skip.py`, `read_heads` (the `full_run` key). `lint/test_push_skip.py`, class `MergedPullRequest`, for the two tests named above.
- **Decision.** `push-skip-on-proven-tree` (a push skips on a proven tree).
- **Retire.** Rename `full_run` to a name that says the run passed. Make the mutation-report test claim no exemption. Add a batch-path test that goes red when the batch path is removed. The closing check is `lint/test_push_skip.py`.
