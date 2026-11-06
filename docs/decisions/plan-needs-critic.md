# Plans need a critic line

## The ruling

Ruling: coordinator, 2026-11-06 12:37 CST, pick a. The owner may rule otherwise.

Each plan record carries a line at line start:

`Critic: <role model>, <date>, <verdict>`

The line may be bold: `**Critic:** <role model>, <date>, <verdict>`. A plan record is a `.md` file that sits directly in the plans home (layout kind `plans`).

## The check

Check: `lint/check_plan_critic.py`, run in CI on pull requests.

- It judges only the plan files that the range adds. Plans already on main are not judged. A plan the range only modifies is not judged either.
- It reads each file as it stands at head. A `Critic:` line that the range adds and then removes again does not count.
- A plan in a subfolder of the plans home is not judged.
- A `Critic:` line inside a fenced code block does not count. Nor does one mid-line, or one with no text after the colon.
- A base it cannot read gives unknown, never a pass.

## Guard need

Risk kind: likely risk. Per `building-guard-needs-incident` (a guard names the mistake it stops):

- Mistake: a lane builds from a plan that nobody critiqued. Triage then reads the plan as vetted.
- Harm: the build rests on a plan that no one has judged.

## Why

A plan built with no second read is a claim with no proof (checks-and-balances audit, 2026-11-06). Protects: a lane's plan has a second read on record.

## Cost

Two git processes to read the range, and one more per judged plan. No file, timer or log.

## Done check

The red cases in `lint/test_check_plan_critic.py` are the Done check. An added plan with no `Critic:` line is flagged. The same plan with the line passes.

Kind: build
Plan: docs/decisions/plan-needs-critic.md#the-ruling (all)
