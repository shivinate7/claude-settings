# Debts have their own store

## The question

Where does a known gap live? Until now, only a decision's "Holes, named" section held a gap that review left open. No list of open gaps existed across decisions.

## The ruling

Every known gap is a debt. The repo keeps a debt store with one entry per debt. Each entry points to its decision, where one exists. Each repo picks its own store. This repo uses `debts/`, one file per debt. Its shape is in `debts/README.md`.

A round-3 limit goes both under "Holes, named" and into a debt file.

The rule is `roles-holes-are-debts`, placed after `roles-review-cap-three` (the three-round review cap).

## Why

The owner ruled on 2026-10-13, 17:40 to 17:47 CDT: all known gaps are to be recorded as debts. Debts get their own place, not only the decision entry. The owner asked for prose guidance, so each repo can build its store as it fits.

The protected outcome: a known gap stays findable in one list, after its decision moves on.

## Grandfathering

On origin/main, the "Holes, named" sections in `decisions/` totaled 34: 32 headings and 2 plain-text mentions (`haiku-prompt-hooks` and `subagent-model-cap`). Each named at least one open hole, with no debt file. The debts-migrate lane filed every hole as a debt file. Each decision with a Holes section now carries one `Debts:` line.

## What protects it

Prose. The rule has an audit row in `lint/rule_mechanisms.json` (kind `unmechanized`) and counts in the pin `UNMECHANIZED_EXPECTED` in `lint/rule_audit.py`. Both landed in 17402e8.

## Holes, named

Debts: `debts-no-check-reads-parts` (no check reads the four parts of a debt file). `debt-decision-link-unchecked` (no check confirms that a debt's decision still names its gap).

Each hole has a debt file in `debts/`.

Kind: process
Home: rule:roles-holes-are-debts
Home: debts/README.md
