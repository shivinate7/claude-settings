# Grandfathered holes have no debt files

- **What.** The "Holes, named" sections in `decisions/` have no debt files yet. They come in two forms: 32 headings, and 2 plain-text mentions. The migration must find both.
- **Where.** The "Holes, named" sections in `decisions/`, on origin/main. The plain-text forms are in `haiku-prompt-hooks` (line 74) and `subagent-model-cap` (line 72).
- **Decision.** `debts-have-their-own-store` (where debts live). Its Grandfathering section names this gap.
- **Retire.** The planned lane debts-migrate files each named hole as a debt file. Then this debt is deleted.
