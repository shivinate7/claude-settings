# The push chain ignores a Red-run line in the chained commit's own message

- **What.** The push-chain refusal ignores a valid Red-run trailer in the chained commit's own `-m`. So `git add <test> && git commit -m m -m "Red-run: ..." && git push` is refused, though it complies. The test-author commits and then pushes in normal work. Workaround: push in a call of its own. Frequency unmeasured. The code lands with #1582 (red-run push check).
- **Where.** `hooks/guard_merge.py`: `_commit_stages_tests`, and the red-chain gate in `conflict_markers_hit`.
- **Decision.** `red-run-trailer-on-test-commits` (red-run trailer on test commits), item 9 (push time). Item 9 lands with #1582 (red-run push check).
- **Retire.** A new case in `hooks/test_guard.py`, red before the fix and green after. When the commit's own message holds a valid Red-run line, the call `git add <test> && git commit -m m -m "Red-run: ..." && git push` is allowed.
