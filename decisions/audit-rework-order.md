# Audit findings are reworked in a fixed order

## The ruling

Owner, 2026-10-16 10:50 CDT. An audit lane works its findings in this order:

1. Delete copies.
2. Merge overlapping entries into tighter lists.
3. Turn number checks into result checks.
4. Fix code.

A prose mandate stays in its central home. Every other record cites it by id and gloss.

The owner gave no reason. No check enforces the order.

Terms, by the orchestrator's call:

- Copy: a second statement of a fact that another entry or rule already holds. Step 1 keeps the home that code or a check reads.
- Number check: passes or fails on a count (rules, lines, bytes). A result check passes or fails on the outcome the count stood for.
- Central home: the CLAUDE.md rule, or the one decision, that owns the question.

Kind: process
Home: rule:speak-cite-id-plus-gloss
Home: rule:git-cite-by-id
Home: rule:outcomes-judge-by-outcome
