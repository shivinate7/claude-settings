# `review_marked` is not the one home of the review log read

- **What.** The read that finds the marked review log comment exists twice on the round-3 head of PR #3190: `review_marked` in `merge/merge.py`, and an inline copy of it. A fix to one copy leaves the other, so the two reads can disagree about which comment is the review log.
- **Where.** `merge/merge.py` on the PR #3190 head: `review_marked` (line 3564) and the inline first-line test in the comment read (line 1138, `first == [REVIEW_MARKER]`). origin/main has no `review_marked`.
- **Decision.** `pr-review-record` (the review log decision; its slug stays under the glossary).
- **Retire.** A case in `merge/test_merge.py` that fails while the read exists in two places, and passes when `review_marked` is the only one.
