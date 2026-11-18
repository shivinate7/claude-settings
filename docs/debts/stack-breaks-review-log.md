# A stacked lane's review log is judged against main

**What.** Lane lint refuses two pull request heads that conflict and says to stack one on the other. After PR 2565 (records only) took in the head of PR 2557 by a merge, `merge --review-record` read 2565's diff against main, saw 2557's code, and refused `--guard no` and kind docs-only. A stacked lane's diff should be read against the head it stacks on. Mistake: Claude follows the stack remedy. Harm: the review log refuses the true kind of the lane, so the lane cannot be logged as it is. Hit twice on 2026-11-10 (PR 2565 on 2557, PR 2566 on 2562). Not run again here.

**Where.** `merge/merge.py`, `--review-record` (the diff it reads for Kind and Guard), and the stack remedy of lane lint.

**Decision.** `pr-review-record` (the review log form and the done rules), and `lanes-run-no-full-ci-job`.

**Retire.** `--review-record` judges Kind and Guard on the diff against the head the lane stacks on. A case in `merge/test_merge.py` takes in another head by merge and expects the lane's own diff to be judged.
