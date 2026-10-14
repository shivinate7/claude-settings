# Debts have their own store

## The question

Where does a known gap live? Until now, only a decision's "Holes, named" section held a gap that review left open. No list of open gaps existed across decisions.

## The ruling

Every known gap is a debt. The repo keeps a debt store with one entry per debt. Each entry points to its decision, where one exists. Each repo picks its own store. This repo uses `debts/`, one file per debt. Its shape is in `debts/README.md`.

The rule is `roles-holes-are-debts`, placed after `roles-review-cap-three` (the three-round review cap). The cap rule stays as written.

## Why

The owner ruled on 2026-10-13, 17:40 to 17:47 CDT: all known gaps are to be recorded as debts. Debts get their own place, not only the decision entry. The owner asked for prose guidance, so each repo can build its store as it fits.

The protected outcome: a known gap stays findable in one list, after its decision moves on.

## Grandfathering

The existing "Holes, named" sections in `decisions/` (34 sections on origin/main) have no debt files. A migration lane, slug `debts-migrate`, files them. Until that lane lands, those holes stay where they are, in their decisions.

## What protects it

Prose. The rule has an audit row in `lint/rule_mechanisms.json` (kind `unmechanized`) and the pin `UNMECHANIZED_EXPECTED` at 76 in `lint/rule_audit.py`. Both landed in 17402e8. The audit crashes on Windows before it checks anchors (see the fourth hole).

## Holes, named

- No check reads `debts/`. `lint/check_record_slugs.py` covers only `decisions/` and `deferred/`, so debt slugs are not checked.
- No check confirms that a debt's decision still names its gap.
- The grandfathered sections (see Grandfathering) have no debt files until `debts-migrate` lands.
- `lint/rule_audit.py` crashes at line 212 on Windows. `subprocess.run(..., text=True)` decodes node output as cp1252. The bug predates this branch.

Each hole has a debt file in `debts/`.

Kind: process
Home: rule:roles-holes-are-debts
Home: debts/README.md
