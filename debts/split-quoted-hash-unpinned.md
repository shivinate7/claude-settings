# No row pins a hash after a space inside a quote

- **What.** Lane merge-guard-b dropped the row `echo a's # b'; pkill foo`. It was the only row that fails when the word-start comment check moves above the quote check. A break there can hide the kill step as a comment, with no red test. The owner chose to merge the lane with this gap on 2026-10-15 17:31 CDT.
- **Where.** `hooks/guard_core.py` near lines 143-149; the kill family in `hooks/test_guard.py` (main line 4488 before the merge).
- **Decision.** `test-strategy-reset` (keep one row per pattern part).
- **Retire.** The row is back, and the moved-check mutant fails it alone.
