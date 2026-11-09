# Records in the plans home need a refuter line

## The ruling

Ruling: coordinator, 2026-11-06 12:37 CST, pick a. The owner may rule otherwise.

Ruling: coordinator, 2026-11-06 12:56 CST, amended by owner item 282 b (via coordinator, 2026-11-06 13:12 CST): the line's word is "refuter". The Refuter line's role must name the refuter role in `hooks/guard_core.py` (`REFUTER_ROLE`, value `refuter`). The check reads `REFUTER_ROLE` from `hooks/guard_core.py`, never a copy. The role is the first word after `Refuter:` (and any `**`), compared case-insensitively. Where `hooks/` is missing or the import fails, the check prints unknown and exits 2.

Each record in the plans home carries a line at line start:

`Refuter: <role> <model>, <date>, <verdict>`

The line may be bold: `**Refuter:** <role> <model>, <date>, <verdict>`. A record is a `.md` file that sits directly in the plans home (layout kind `plans`).

## The check

Check: `lint/check_plan_refuter.py`, run in CI on pull requests.

- It judges only the records in the plans home that the range adds. Records already on main are not judged.
- It reads each file as it stands at head. A `Refuter:` line that the range adds and then removes again does not count.
- A file in a subfolder of the plans home is not judged.
- A `Refuter:` line inside a fenced code block does not count. Nor does one mid-line.
- A `Refuter:` line counts only if the first word after the colon (and any `**`, with spaces between) is the refuter role. A `<...>` placeholder, a planner or reviewer role, and a longer word that starts with the role do not count.
- A base it cannot read gives unknown, never a pass.

## Limits

A record that the range only modifies, such as one rewritten in place, is not judged. Only an added record is. A line that opens with a triple-backtick code span, with backticks later on the same line, opens no fence. It never counts as a `Refuter:` line.

The check reads the word, not the writer. An orchestrator can type `Refuter: refuter <model>, <date>, <verdict>` with no refuter spawned, and the check passes it. The role check closes only the gap where any role word passes. Residual: a typed refuter line with no refuter behind it still passes.

## Guard need

Risk kind: likely risk. Per `building-guard-needs-incident` (a guard names the mistake it stops):

- Mistake: a lane builds from a record that no refuter read. Triage then reads the record as vetted.
- Harm: the build rests on a record that no one has judged.

## Why

A plan built with no second read is a claim with no proof (checks-and-balances audit, 2026-11-06). Protects: a lane's plan has a second read on record.

## Cost

Two git processes to read the range, and one more per judged record. No file, timer or log.

## Done check

The red cases in `lint/test_check_plan_refuter.py` are the Done check. An added record with no `Refuter:` line is flagged. The same record with the line passes.

Kind: build
Plan: docs/decisions/plan-needs-refuter.md#the-ruling (all)
