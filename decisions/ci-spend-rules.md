# ci-hygiene carries five rules that cut CI spend

## What was measured

Measured 2026-10-06 on ssemwal-cdc/q_max (a private repo). About 9,400 runner minutes in
5.8 days, 95% of it the `gate` workflow. One PR push cost about 30 minutes across 11 jobs:
4 test shards 19, `specimen` 3, five jobs about 1 each. One PR made 68 runs, 18% of all
spend. 86 runs failed at about 25 minutes each, because the test shards ran after a
1-minute static check failed. No schedule ran. GitHub stopped starting jobs when billing
failed, and nobody saw the spend first.

## The ruling

Skill steps 1 and 11 to 14 hold these rules. Read billed minutes weekly and set a spending
alarm. Run no CI on a draft. Run cheap checks first through `needs:`. Merge jobs under a
minute. Cache the install.
The owner chose "Both, skill first" on 2026-10-06.

- A draft cannot merge, so a draft needs no required check. The checks run on
  `ready_for_review`.
- The billing read has no opt-in template. A workflow `GITHUB_TOKEN` cannot read the user
  billing endpoint, so an alarm would need a stored personal token. The skill gives the
  command and points at the budget alert in the billing settings.
- Unmeasured: the saving of each rule on a real repo.
