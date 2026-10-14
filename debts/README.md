# Debts

A debt is a known gap. The rule `roles-holes-are-debts` in `CLAUDE.md` makes every known gap a debt. This folder is the debt store for this repo.

## Shape

One file per debt, named by a slug of 32 characters or fewer. Each file has four parts:

- **What.** The gap, in one or two sentences.
- **Where.** The file, rule, or check the gap sits in.
- **Decision.** The decision that names the gap, by slug plus a short gloss. Use the slug now. If the repo numbers decisions, add the number at merge. Never cite it by path. If no decision exists, write `none`.
- **Retire.** What closes the gap, and the check that shows it closed.

## Closing a debt

In the PR that closes the gap, delete the debt file. If a decision names the gap, rewrite that decision's entry in place, so it no longer lists the gap. Git keeps the history.

## Status

No check reads the structure of this folder yet. `lint/check_record_slugs.py` does not cover it, so the slug length is a convention only. The "Holes, named" sections in `decisions/` are grandfathered: they stay where they are until the planned lane debts-migrate files them.
