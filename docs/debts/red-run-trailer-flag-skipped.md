# A Red-run trailer given with --trailer is not read

- **What.** `git commit -m m --trailer "Red-run: none: x" && git push` is refused, though the commit's message gets a valid Red-run trailer from `--trailer`. `--trailer` takes a value, so `_commit_paragraphs` skips that value and reads only the `-m` text. Frequency unmeasured. The round 3 review judged it likely in normal work.
- **Where.** `hooks/guard_merge.py`: `_commit_paragraphs`. `--trailer` is in `_COMMIT_VALUE_FLAGS` but not in `_MESSAGE_ELSEWHERE`.
- **Decision.** `red-run-trailer-on-test-commits` (red-run trailer on test commits), item 9 (push time).
- **Retire.** A new case in `hooks/test_guard.py`, red before the fix and green after. `git commit -m m --trailer "Red-run: none: x" && git push` is allowed, and the same call with no trailer is refused.
