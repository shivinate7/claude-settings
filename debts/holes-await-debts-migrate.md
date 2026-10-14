# Grandfathered holes have no debt files

- **What.** The "Holes, named" sections in `decisions/` have no debt files yet.
- **Where.** The "Holes, named" sections in `decisions/`, on origin/main.
- **Decision.** `debts-have-their-own-store` (where debts live). Its Grandfathering section names this gap.
- **Retire.** Lane `debts-migrate` files each named hole as a debt file. Then this debt is deleted.
