# ci-hygiene carries five rules that cut CI spend

## The ruling

Owner, 2026-10-06 ("Both, skill first"): skill steps 1 and 11 to 14 hold these rules.

- Read billed minutes weekly and set a spending alarm.
- Run no CI on a draft. A draft cannot merge, so it needs no required check. The checks run on `ready_for_review`.
- Run cheap checks first through `needs:`.
- Merge jobs under a minute.
- Cache the install.
- The billing read has no opt-in template. A workflow `GITHUB_TOKEN` cannot read the user billing endpoint. The skill gives the command and points at the budget alert in the billing settings.

Why: CI spend grew unseen until billing failed. Unmeasured: the saving of each rule on a real repo.

Kind: process
Home: skills/ci-hygiene/SKILL.md
