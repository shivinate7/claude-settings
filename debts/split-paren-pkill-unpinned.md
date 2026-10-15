# No row pins a kill step after an apostrophe and a parenthesis

- **What.** Lane merge-guard-b dropped the row `echo don't (x; pkill foo`. It was the only row that fails when the splitter's second reading goes (`if open_quote and shaped`). A break there lets that kill step pass with no red test. The owner chose to merge the lane with this gap on 2026-10-15 17:31 CDT.
- **Where.** `hooks/guard_core.py` near line 123; the kill family in `hooks/test_guard.py` (main line 4496 before the merge).
- **Decision.** `test-strategy-reset` (keep one row per pattern part).
- **Retire.** The row is back, and a mutant of the second reading fails it alone.
