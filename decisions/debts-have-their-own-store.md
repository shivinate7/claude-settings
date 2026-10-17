# Debts have their own store

## The ruling

A known gap that Claude is likely to hit in normal work is a debt. The repo keeps a debt store with one entry per debt, each pointing to its decision where one exists. Each repo picks its own store. This repo uses `debts/`, one file per debt. Its shape is in `debts/README.md`.

Owner, 2026-10-17 11:56 CDT: any other finding is one line in `debts/notes.md`, with no red test and no decision edit. A note becomes a debt after a real incident.

A round-3 limit goes under "Holes, named". It also goes into a debt file, or a line in the notes file.

The rule is `roles-holes-are-debts`, placed after `roles-review-cap-three` (the three-round review cap).

Why: a likely gap stays findable in one list after its decision moves on. Only a likely gap costs a debt file.

## Holes, named

Debts: `debts-no-check-reads-parts` (no check reads the four parts of a debt file). `debt-decision-link-unchecked` (no check confirms that a debt's decision still names its gap).

Kind: process
Home: rule:roles-holes-are-debts
Home: debts/README.md
