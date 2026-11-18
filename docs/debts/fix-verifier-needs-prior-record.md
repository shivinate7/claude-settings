# A fix verifier cannot be logged when the round before it was never posted

**What.** `merge --review-record --fix-check` refuses (exit 2) unless HEAD is the Head of the newest earlier review log comment on the pull request. Once the head moves past a round that nobody posted, that round cannot be logged again, so its fix verifier cannot be logged either. Mistake: a lane or a reviewer ends a round without posting its log. Harm: the pull request cannot reach done by the normal route. Seen on PR 2480 (2026-11-09 19:50 CST) and on Degen PR 560 (2026-11-09 12:52 CST). The rule that a fix check follows a record is owner item 741, so the gap is the unposted round, not the rule.

**Where.** `merge/merge.py`, `--review-record` with `--fix-check` (the "newest earlier record" read).

**Decision.** `pr-review-record` (the review log form and the done rules).

**Retire.** Either `--review-record` can log a past round at its own reviewed sha, or each round posts its own log at its end (step record-tool-posts-itself). A case in `merge/test_merge.py` runs `--fix-check` on a head whose earlier round was never posted and expects the route the fix names.
