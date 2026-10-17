# Debts have their own store

## The question

Where does a known gap live?

## The ruling

A known gap that Claude is likely to hit in normal work is a debt. The repo keeps a debt store with one entry per debt. Each entry points to its decision, where one exists. Each repo picks its own store. This repo uses `debts/`, one file per debt. Its shape is in `debts/README.md`.

Owner ruling, 2026-10-17 11:56 CDT: any other finding is one line in the store's notes file, `debts/notes.md`, with no red test and no decision edit. A note becomes a debt after a real incident.

A round-3 limit goes under "Holes, named". It also goes into a debt file, or a line in the notes file.

The rule is `roles-holes-are-debts`, placed after `roles-review-cap-three` (the three-round review cap).

## Why

The owner ruled on 2026-10-13, 17:40 to 17:47 CDT: all known gaps are to be recorded as debts. Debts get their own place, not only the decision entry. The owner asked for prose guidance, so each repo can build its store as it fits. On 2026-10-17 the owner cut the debt count: only a gap that Claude is likely to hit costs a debt file.

The protected outcome: a gap that Claude is likely to hit stays findable in one list, after its decision moves on.

## What protects it

Prose. The rule has an audit row in `lint/rule_mechanisms.json` (kind `unmechanized`) and counts in the pin `UNMECHANIZED_EXPECTED` in `lint/rule_audit.py`.

## Holes, named

Debts: `debts-no-check-reads-parts` (no check reads the four parts of a debt file). `debt-decision-link-unchecked` (no check confirms that a debt's decision still names its gap).

Each hole has a debt file in `debts/`.

Kind: process
Home: rule:roles-holes-are-debts
Home: debts/README.md
