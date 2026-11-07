# The round floor's why hides the fix check's why

**What.** Say the newest record on a PR has a Fix check FAIL or WIDE, and an earlier record set a floor. Then `merge --reviewed` prints the floor's why in place of `review_state`'s own. The state is right. The why is wrong. A WIDE reader is told to reach round 2 or post a fix PASS. The why should say the fix needs a new lane at round 1. A FAIL reader loses "the next record carries Round N+1". Found by review round 3 of PR 1440 (a failed fix check counts as the next round), 2026-11-07.

**Where.** `merge/merge.py`, `reviewed_lines`, where the `round_floor` why replaces the `review_state` why.

**Decision.** pr-review-record (the review record).

**Retire.** When the newest record has a Fix check FAIL or WIDE, print `review_state`'s why, or join both whys. Add a test in `merge/test_merge.py` `ReviewedList` that pins the WIDE text "new lane at round 1" under an earlier floor.
