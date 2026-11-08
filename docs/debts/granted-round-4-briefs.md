# A granted round 4 has no reviewer text

- **What.** The review record accepts a granted round 4, which is the final round. The reviewer file still says round 3 is the last round and holds the net-value lines, so a round 4 reviewer is not told to write them. The record stays open until a net value is written, so the gap fails closed.
- **Where.** `agents/reviewer.md`, the Rounds paragraph.
- **Decision.** `pr-review-record` (the review record), and `hold-unsafe-after-round-3` (net-value hold after round 3).
- **Retire.** The Rounds paragraph says that a granted round 4 is the last round and holds the net-value lines. The test is `hooks/test_guard.py`.
