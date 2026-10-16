# No case pins the reload wait for a missing hook file

- **What.** Lane merge-guard-b removed `_damage_missing` and its two reload cases: a missing `guard_pointer.py` that comes back during the wait is allowed, and one that stays missing is refused. No kept case covers a missing file during the wait. The fail-closed rows check the refusal only. The owner chose to merge the lane with this gap on 2026-10-15 17:31 CDT.
- **Where.** The reload-stamp cases in `hooks/test_guard.py` (main lines 10305 and 10412-10414 before the merge); the reload wait in `hooks/guard.py`.
- **Decision.** `test-strategy-reset` (keep one row per filter).
- **Retire.** Both cases are back and pass, or a merged case covers both outcomes.
