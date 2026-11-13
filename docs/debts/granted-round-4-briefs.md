# A granted round 4 has no reviewer text and no free model row

- **What.** The review record now accepts a granted round 4, which is the final round. The reviewer file still says round 3 is the last round and holds the net-value lines, so a round 4 reviewer is not told to write them. The record stays open until a net value is written, so the gap fails closed. The model guard frees Sonnet only for `Round 2 of 3` and `Round 3 of 3`, so a round 4 reviewer on Sonnet is refused.
- **Where.** `agents/reviewer.md`, the Rounds paragraph. `hooks/guard.py`, `ROLE_REVIEWER_FREE_ROUNDS`.
- **Decision.** `pr-review-record` (the review record), and `hold-unsafe-after-round-3` (net-value hold after round 3).
- **Retire.** The Rounds paragraph says that a granted round 4 is the last round and holds the net-value lines. The guard lets a `Round 4 of 4` reviewer brief run Sonnet. The test is `hooks/test_guard.py`.
