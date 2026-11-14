# A Red-run trailer given with --trailer is not read

- **What.** `git commit -m m --trailer "Red-run: none: x" && git push` is refused, though the commit's message gets a valid Red-run trailer from `--trailer`. `--trailer` takes a value, so `_commit_paragraphs` skips that value and reads only the `-m` text. Not covered: no case in tests/guard/s43400-red-run-push.py passes `--trailer`. Frequency unmeasured. The round 3 review judged it likely in normal work.
- **Where.** `hooks/guard_merge.py`: `_commit_paragraphs`. `--trailer` is in `_COMMIT_VALUE_FLAGS` but not in `_MESSAGE_ELSEWHERE`.
- **Decision.** `red-run-trailer-on-test-commits` (red-run trailer on test commits), item 9 (push time).
- **Retire.** Close this debt with a Retire-run cite in the PR body (`Retire-run: <slug> -- <passing CI run URL>`) naming a green CI run of the guard suite on the PR head. Close it only after a case exists in tests/guard/s43400-red-run-push.py. The case: `git commit -m m --trailer "Red-run: none: x" && git push` is allowed. The same call with no trailer is refused.
