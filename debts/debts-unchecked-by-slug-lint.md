# Debt slugs are not checked

- **What.** Debt file slugs get no length or name check. `lint/check_record_slugs.py` covers only `decisions/` and `deferred/`.
- **Where.** `lint/check_record_slugs.py`, the `DIRS` line.
- **Decision.** `debts-have-their-own-store` (where debts live).
- **Retire.** Add `debts/` to `DIRS`. Then a debt file with a slug over 32 characters fails the check.
