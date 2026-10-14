# No check reads the four parts of a debt file

- **What.** No check reads the four parts of a debt file. `lint/check_record_slugs.py` checks only the slug length.
- **Where.** `lint/check_record_slugs.py` and the debt files in `debts/`.
- **Decision.** `debts-have-their-own-store` (debts have their own store).
- **Retire.** A check reads What, Where, Decision and Retire in each file. A test with a file that lacks a part goes red.
