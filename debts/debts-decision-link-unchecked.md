# No check confirms a debt's decision still names its gap

- **What.** No check confirms that a debt's decision still names its gap.
- **Where.** The debt files in `debts/`, and the decisions they cite.
- **Decision.** `debts-have-their-own-store` (debts have their own store).
- **Retire.** A check finds each debt's decision and its gap line. A test with a decision that drops the gap goes red.
