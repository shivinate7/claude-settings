# Debts

A debt is a known gap that stays open after review round 3. The rule `roles-holes-are-debts` in `CLAUDE.md` makes each named hole a debt. This folder is the debt store for this repo.

## Shape

One file per debt, named by a slug of 32 characters or fewer. Each file has four parts:

- **What.** The gap, in one or two sentences.
- **Where.** The file, rule, or check the gap sits in.
- **Decision.** The decision record whose "Holes, named" section names the gap. Cite it by id plus a short gloss, never by path.
- **Retire.** What closes the gap, and the check that shows it closed.

## Retire a debt

In the PR that closes the gap, delete the debt file. Rewrite the decision's "Holes, named" entry in place, so it no longer lists the gap. Git keeps the history.

## Status

No check reads this folder yet. `lint/check_record_slugs.py` does not cover it, so the slug length is a convention only. Existing holes in `decisions/` are not migrated.
