# A brief can state a code fact that no one read this turn

**What.** A coordinator brief stated, from memory, that the review-record post runs the STE lint. It did not. The lane checked main and caught it before it built on the claim. A lane that does not check builds on a false premise, or spends a review round on it. Claude is likely to do this again: a brief is written fast, from what the session last knew.

**Where.** Coordinator and orchestrator briefs, sent with `send_message` or the Agent tool. No reader judges them.

**Decision.** `verification-report-unknown-reads`, verify a claim before you rely on it.

**Retire.** A check that reads a brief and finds each code fact (a file, symbol, flag or behaviour) with no read of that file in the same turn. Until then, each brief cites the file and symbol it read for each code fact. Closed when a guard case refuses a brief with an unread code fact and allows the same brief with its read.
