# Test comments cite deleted records

- **What.** Comments in tests still name records and plans that were deleted, or sections that moved. A reader who follows the name finds nothing. A builder may not edit test files, so a test-author re-points them.
- **Where.** `hooks/test_guard.py` (stash push forms, discard forms, agent-owned carve-out), `hooks/test_decision_watch.py`, `hooks/test_rm_prompt_answer.py`, `merge/test_merge.py`, `lint/test_ste_autofix.py`.
- **Decision.** `plain-prose-lint` (the STE lint becomes a plain-prose lint), hole 10.
- **Retire.** A test-author re-points each comment to a live record. A sweep of every cited record name then finds none missing.
