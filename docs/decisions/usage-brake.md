# Usage at 90% winds work down and 94% stops new work (account scope unconfirmed)

## The ruling

Owner, 2026-11-11 13:48 CST, relayed by the retrospective session. Quoted exactly:

> "it might just be somehow local in my mac's coordinators handoffs and not on claude-settings anywhere but ya it was basically just that after usage hits 90% everything looks to gently wind down and 94% is a hard brake"

The owner's words give no account scope. Sources: roadmap step `usage-brake` (fields `source` and `note`), and restart-plan item R43 (the usage brake), in `docs/plans/restart-plan.md`.

The owner said the ruling may be local to a Mac coordinator's handoffs. At 13:49 CST the retrospective found no record, hook or page item that held it.

### The retrospective's reading: UNCONFIRMED

This reading goes to the owner for correction. It is not the owner's words. The scope in it is the retrospective's (restart-plan item R43).

- On an account with a 5-hour or weekly limit, at 90% no new lane or agent starts. Running work finishes and writes its handoff.
- At 94%, every session stops new work.
- An account with no limit never brakes.

The retrospective reads the third point as consistent with the owner's 2026-11-01 17:56 CST ruling. Its recorded words, in `docs/decisions/session-tiers.md` (line 28), are "There is no usage limit". The retrospective reads that ruling as being about session length (`docs/plans/restart-plan.md`, item R43). That reading is the retrospective's, not the owner's.

Open question for the owner: does the no-limit ruling conflict with the brake reading?

## Why

A rate-limited account that runs out mid-work loses unsaved work. Source: roadmap step `usage-brake`, field `why`.

Unmeasured: how often an account runs out mid-work, and how much unsaved work each time is lost.

## Before any build

The first step is a lane measurement: can a hook read the usage percentages? Today this is unmeasured on most surfaces.

What main has. The check covered the whole tree of this branch (origin/main 39e378f15 plus this record), all file types, excluding `.git` and `node_modules`. The terms were `rateLimits`, `percentUsed`, `five_hour` and `seven_day`.

- One reader of the percentages: the desktop status line mod, `mods/desktop-statusline/hooks/register.tsx`. Its `refresh` reads `$.session.usage()` (line 113) and maps `usage.rateLimits` to `percentUsed` (lines 144 to 146). If `isOnDesktop` does not hold, it returns early (line 110). So it reads on the desktop surface only.
- Its warnings fire at 80% and at 95% (`WARN_AT`, line 16). They do not fire at the brake's 90% and 94%.
- Two other mods call `$.session.usage()` for context fill, not for rate limits: `mods/session-board/hooks/register.mjs` (line 358) and `mods/token-weather/hooks/token-weather.mjs`.
- A test file, `mods/desktop-statusline/desktop-statusline.test.mjs`, mocks `rateLimits`. It reads none.

Unmeasured: whether a cloud session or a terminal hook can read the percentages.

Unmeasured: where the host gets the percentages. The value comes through the engine's `$.session.usage()`. This repo does not show its source.

The code home is not named on main. The first lane names it after the measurement.

## Handoff case

The owner's words say the ruling may be local to a Mac coordinator's handoffs. A ruling should reach a tracked home at once (`docs/decisions/precompact-handoff.md`, item 5).

No guard id on main names this case. The nearest guards are `handoff-sections` and `handoff-checked-stamp` in `hooks/guard.py`. They check section names and premise stamps in a handoff. They do not check rulings.

This ruling is a case for a guard that refuses a ruling kept only in a handoff. Main has no such guard.

## When this record changes

This record changes when the first lane measures whether a hook can read the usage percentages on each surface. It also changes when the owner corrects the reading or answers the open question.

Kind: build
Plan: docs/decisions/usage-brake.md#the-ruling (all)
