# Debts have their own store

## The question

Where does a gap live after review round 3 leaves it open? Until now, only the decision's "Holes, named" section held it. No list of open gaps existed across decisions.

## The ruling

Each named hole is also a debt. The repo keeps a debt store with one entry per debt, and each entry points to its decision. Each repo picks its own store. This repo uses `debts/`, one file per debt. Its shape is in `debts/README.md`.

The rule is `roles-holes-are-debts`, placed after `roles-review-cap-three` (the three-round review cap). The cap rule stays as written.

## Why

The owner ruled on 2026-10-13, 17:40 to 17:47 CDT: every known gap left after round 3 is a debt, and debts get their own place. The owner asked for prose guidance, so each repo can build its store as it fits.

The protected outcome: a gap that round 3 leaves open stays findable in one list, after its decision moves on.

## What protects it

Prose only for now. The `roles-holes-are-debts` row in `lint/rule_mechanisms.json` is not on this branch. Until a builder lands that row and the pin change, the rule audit fails on the new anchor.

## Holes, named

- No check reads `debts/`. `lint/check_record_slugs.py` covers only `decisions/` and `deferred/`, so debt slugs are not checked.
- No check confirms that a debt's decision still names its gap.
- Existing "Holes, named" sections in `decisions/` are not migrated. A later lane files them.
- The rule's audit row and its pin change are not on this branch. Until they land, the rule audit fails on this anchor.

Kind: process
Home: rule:roles-holes-are-debts
Home: debts/README.md
