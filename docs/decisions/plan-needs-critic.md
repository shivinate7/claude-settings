# Records in the plans home need a critic line

## The ruling

Ruling: coordinator, 2026-11-06 12:37 CST, pick a. The owner may rule otherwise.

Ruling: coordinator, 2026-11-06 12:56 CST. The Critic line's role must name the challenger role in `hooks/guard_core.py` (`CHALLENGER_ROLE`). The change waits on lane `blind-plan-refuter`.

Each record in the plans home carries a line at line start:

`Critic: <role model>, <date>, <verdict>`

The line may be bold: `**Critic:** <role model>, <date>, <verdict>`. A record is a `.md` file that sits directly in the plans home (layout kind `plans`).

## The check

Check: `lint/check_plan_critic.py`, run in CI on pull requests.

- It judges only the records in the plans home that the range adds. Records already on main are not judged.
- It reads each file as it stands at head. A `Critic:` line that the range adds and then removes again does not count.
- A file in a subfolder of the plans home is not judged.
- A `Critic:` line inside a fenced code block does not count. Nor does one mid-line.
- A `Critic:` line counts only if a word character follows the colon (and any `**`, with spaces between). A `<...>` placeholder does not count.
- A base it cannot read gives unknown, never a pass.

## Limits

A record that the range only modifies, such as one rewritten in place, is not judged. Only an added record is. A line that opens with a triple-backtick code span reads as a fence, so it never counts as a `Critic:` line.

## Guard need

Risk kind: likely risk. Per `building-guard-needs-incident` (a guard names the mistake it stops):

- Mistake: a lane builds from a record that nobody critiqued. Triage then reads the record as vetted.
- Harm: the build rests on a record that no one has judged.

## Why

A plan built with no second read is a claim with no proof (checks-and-balances audit, 2026-11-06). Protects: a lane's plan has a second read on record.

## Cost

Two git processes to read the range, and one more per judged record. No file, timer or log.

## Done check

The red cases in `lint/test_check_plan_critic.py` are the Done check. An added record with no `Critic:` line is flagged. The same record with the line passes.

Kind: build
Plan: docs/decisions/plan-needs-critic.md#the-ruling (all)
