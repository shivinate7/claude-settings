# Old-form write after a named record

**What.** A plain write may post an old-form record (its rounds carry no `:SHA`) after any earlier record, even one whose rounds name heads. Scenario: an earlier named record lists stale. Claude reposts it old-form with the live Head. The write succeeds and the listing reads done, which sidesteps the rule that a records-only commit needs a fix check record. Harm: code merges on a review that did not read the live head. The gap is the same on main, so PR 2277 did not open it.

**Where.** `merge/merge.py` `main`, the plain path's first-record check: the `not earlier ... len(a.round[0]) == 4` branch. Its comment says a write after an earlier record keeps the old form, which is the gap.

**Decision.** `pr-review-record` (the review record).

**Retire.** Fix: refuse an old-form write when any earlier record names heads, with exit 2 and no record. A case in `merge/test_merge.py` posts an earlier named record, then an old-form write at the live Head, and expects exit 2.
