# Code comments cite deleted records

- **What.** Comments in code and tests still name records and plans that were deleted. A reader who follows the name finds nothing.
- **Where.** `janitor/sweep.py`, `hooks/guard_frozen.py`, `hooks/guard.py`, `hooks/test_guard.py`, `hooks/test_decision_watch.py`, `hooks/config_watch.py`, `merge/test_merge.py`, `lint/test_gates.py`, `lint/test_ste_autofix.py`, `mods/plain-diff/docs/mockup.html`.
- **Decision.** `plain-prose-lint` (the STE lint becomes a plain-prose lint), hole 10.
- **Retire.** The comment-cites lane re-points each comment to a live record.
