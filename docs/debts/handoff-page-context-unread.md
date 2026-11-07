# A waiting-page task's "Why yours" context is not judged

**What.** The "Why yours" line in a waiting-page task's `context` is not judged. `hooks/question_form.py` checks only that the line exists (:789 pattern, used at :801), so a false capability reason in it passes.

**Where.** `hooks/question_form.py`, WHY_YOURS_LINE and its context check (:789, :801).

- **Decision.** `none`.

**Retire.** A test feeds a task context whose "Why yours" line gives a capability reason with no cite, and expects a refusal. The same line with a cite passes.
