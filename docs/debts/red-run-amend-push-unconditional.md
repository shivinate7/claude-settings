# The push chain refuses every amend that a push follows in the same call

- **What.** Any `git commit --amend` followed by a push in the same call is refused as a red-run chain, even when the amend is docs-only. The gate reads the `--amend` flag, not the amended content. Workaround: push in a call of its own. Frequency unmeasured. The code lands with #1582 (red-run push check).
- **Where.** `hooks/guard_merge.py`: `_commit_stages_tests`, its first test (`--amend` in the call).
- **Decision.** `red-run-trailer-on-test-commits` (red-run trailer on test commits), item 9 (push time). Item 9 lands with #1582 (red-run push check).
- **Retire.** A new case in `hooks/test_guard.py`, red before the fix and green after. It allows a docs-only amend followed by a push in one call, and still refuses an amend that adds test lines followed by a push.
