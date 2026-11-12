# On a rate-limited account, usage at 90% winds work down and 94% stops new work

## The ruling

Owner, 2026-11-11 13:48 CST, relayed by the retrospective session. Quoted exactly:

> "it might just be somehow local in my mac's coordinators handoffs and not on claude-settings anywhere but ya it was basically just that after usage hits 90% everything looks to gently wind down and 94% is a hard brake"

Sources: roadmap step `usage-brake` (fields `source` and `note`), and restart-plan item R43 (the usage brake), in `docs/plans/restart-plan.md`.

The owner said the ruling may be local to a Mac coordinator's handoffs. At 13:49 CST the retrospective found no record, hook or page item that held it.

### The retrospective's reading: UNCONFIRMED

This reading goes to the owner for correction. It is not the owner's words.

- On an account with a 5-hour or weekly limit, at 90% no new lane or agent starts. Running work finishes and writes its handoff.
- At 94%, every session stops new work.
- An account with no limit never brakes.

The third point is consistent with the owner's 2026-11-01 17:56 CST ruling. That ruling says there is no usage limit, and a standing session runs until autocompact (`docs/decisions/session-tiers.md`, the compaction bullet). It covers session length, not a usage limit. It does not settle the brake.

## Why

A rate-limited account that runs out mid-work loses unsaved work. Source: roadmap step `usage-brake`, field `why`.

Unmeasured: how often an account runs out mid-work, and how much unsaved work each time is lost.

## Before any build

The first step is a lane measurement. The lane checks whether a hook can read the usage percentages. Today this is unmeasured.

A grep of `hooks/` and `lint/` for usage-percentage names found no reader on main, on 2026-11-12. Unmeasured: whether a hook can read the percentages at all.

Unmeasured: where the percentages come from. This record names no source for them.

The code home is not named on main. The first lane names it after the measurement.

## Handoff case

The owner's words say the ruling may be local to a Mac coordinator's handoffs. A ruling should reach a tracked home at once (`docs/decisions/precompact-handoff.md`, item 5).

No guard id on main names this case. The nearest guards are `handoff-sections` and `handoff-checked-stamp` in `hooks/guard.py`. They check section names and premise stamps in a handoff. They do not check rulings.

This ruling is a case for a guard that refuses a ruling kept only in a handoff. Main has no such guard.

## When this record changes

This record changes when the first lane measures whether a hook can read the usage percentages. It also changes when the owner corrects the reading.

Kind: build
Plan: docs/decisions/usage-brake.md#the-ruling (all)
