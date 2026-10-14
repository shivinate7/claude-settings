# Debt decision link is not checked

- **What.** No check confirms that a debt's decision still names its gap.
- **Where.** The link between `debts/` and the "Holes, named" sections in `decisions/`. No check reads the structure of either side.
- **Decision.** `debts-have-their-own-store` (where debts live).
- **Retire.** A check that reads each debt's decision and goes red when the decision does not name the gap.
