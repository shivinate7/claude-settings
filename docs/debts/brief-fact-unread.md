# A brief can state a code fact that no one read this turn

**What.** A coordinator brief stated, from memory, that the review-record post runs the STE lint. It did not. The lane checked main and caught it before it built on the claim. A lane that does not check builds on a false premise, or spends a review round on it. Claude is likely to do this again: a brief is written fast, from what the session last knew.

**Where.** Lane briefs that a coordinator sends with `send_message`. Step brief-claim-has-probe (#1664) judges Agent spawns of a builder or test-author only, so a lane brief has no reader.

**Decision.** `verification-report-unknown-reads`, verify a claim before you rely on it.

**Retire.** Extend the home of brief-claim-has-probe (#1664) to a `send_message` whose text starts with `Lane brief:`. Until then, each lane brief cites the file and symbol it read for each code fact. Closed when a guard case refuses a lane brief with an unprobed code fact and allows the same brief with its probe.
