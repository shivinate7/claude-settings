# An Important finding below the verdict line does not block

**What.** `parse_review` in `merge/merge.py` ends a review record at its first `---` line and reads nothing below it. The review-log guard judges only the lines above it. So blocking rests on the Round lines alone. A record whose Round lines read PASS, with an open `[Important]` finding below `---`, reads done.

**Where.** `merge/merge.py`, `parse_review` and `review_state`. `hooks/guard_review_log.py`. `docs/decisions/pr-review-record.md`, the findings bullet, which states that blocking rests on the verdict line.

**Decision.** `pr-review-record` (the review record form, which says blocking rests on the verdict line above `---`).

**Retire.** Not yet built. Write a case in `merge/test_merge.py` first, red on the current code: a record with a PASS Round line and an open `F1 [Important]` line below `---` must read open in `review_state`. The case goes green when the merge tool reads the findings below the rule.
