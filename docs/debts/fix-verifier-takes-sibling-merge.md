# The fix verifier accepts a fix head that merges two lane commits

**What.** `merge <pr> --review-record --fix-check` accepts a fix head that is a merge of two lane commits. Only a merge of main should pass. Queued step `fix-verifier-takes-sibling-merge`, queued in chat on Nov 18-19. Not reproduced yet, so unmeasured.

**Where.** `merge/merge.py`, the `--fix-check` branch of `--review-record`. It accepts a merge when the head has two parents and `holds_head_gh` reads that the base holds the second parent. A second parent that is a lane commit already on the base passes that read. The usage text of `merge/merge.py` says the second parent must be on the base.

**Decision.** `pr-review-record` (the review record, its `Fix check` line, and the fix verifier rules).

**Retire.** `merge/test_merge.py` holds a case, red first on the current code, where `--fix-check` refuses a fix head that merges two lane commits and passes a fix head that merges main.

## Ruling

Owner approved this at 00:16 CST Nov 19.
