# A passed fix check skips the top-round head check

- **What.** A passed fix check skips the top-round head check. The fix base must be the earlier record's Head, not the named round head. Scenario: round 1 PASS names H0, the record's Head is H1, and a fix check from H1 reads done, though no one read H0 to H1. Claude reaches it when a push lands between the review and the record write. The base read an old-form record at H1 as done outright, so this is no new hole.
- **Where.** `merge/merge.py` `review_state` (the head check a passed fix check skips) and `fix_base_problem` (the fix base it reads).
- **Decision.** pr-review-record (the review record).
- **Retire.** Rewrite `review_state` and `fix_base_problem` so the fix base is the earlier record's Head. A case in `merge/test_merge.py` pins the scenario above.
