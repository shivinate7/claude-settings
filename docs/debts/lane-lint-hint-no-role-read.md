# Lane lint prints the build command with no role read

- **What.** `lane_lint` calls `combine_hint(root, host)` with no exclude and no trigger. At the backlog, the hint's build branch then prints the train build command to any session that runs a lane lint, without reading that session's role. Only a batch runner should get that command.
- **Where.** `merge/merge.py` `lane_lint`, the `combine_hint(root, host)` call (skipped only when `pre_join` is set), and the build branch of `combine_hint`.
- **Decision.** `session-tiers`, bullet "Batch runner" (who may build a batch; the consultant's hat, owner 20:49 CST Nov 25).
- **Retire.** A case in `merge/test_merge.py` shows that a lane lint run by a session that is not a batch runner prints no build command. Not built: the case is not written yet.
