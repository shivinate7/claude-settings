# A step record's lane field asks even when the named session holds no step

- **What.** After a whole list read with no carrier, rule `lane-step-dup` asks whenever a step record's `lane` field names another session. That holds even when the session is archived or holds another step. About 164 of 388 todo or ready step records name a session (measured on the roadmap branch, 2026-11-09). The stated remedy is a write to the record branch.
- **Where.** `hooks/guard_merge.py` `_step_held_hit`, reason `STEP_DUP_RECORD_REASON`.
- **Decision.** `session-tiers` (the session shapes; the lane-step-dup bullet).
- **Retire.** The narrowing change lands. A `lane` field that names a session appearing in the whole list read's rows, with no `cs-step` tag for the step, gives no verdict. It ships a case in family `lane-step-dup` in `hooks/test_guard.py`, which runs green. The narrowing PR is stacked on PR 2328, so this debt closes when that PR merges.
