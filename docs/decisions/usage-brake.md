# Usage at 90% is cautious, 93% starts wind-down, 97% is a hard stop

## The ruling

Owner, 2026-11-26 13:57 CST, the newest words. Quoted exactly:

> "ya make it basically 90% is cautious, 93% is the wind down beginning, 97% hard stop"

On close items the owner said: "This should be resumed to land". On the new-work line he said: "this should be 90%".

Far work: owner, 2026-11-26 13:47 CST. Its work is saved, committed, and marked in the handoff as part of its agenda.

It replaces R43 (restart-plan item R43, owner 2026-11-11 13:48 CST) and the earlier numbers.

## The rule

- At 90% usage, cautious. Start no new work.
- At 93%, wind-down begins.
  - Work close to main: resume it to land.
  - Work far from main: save and commit it. Mark it in the session's handoff as part of its agenda.
- At 97%, hard stop. All agents stop.

## Why

The gap from 93% to 97% leaves room to land close work and save far work before the hard stop.

Unmeasured: how often an account runs out mid-work, and how much unsaved work each time is lost.

## Account scope: unconfirmed

The owner's words give no account scope. The retrospective's reading, for the owner to correct: the brake applies to an account with a 5-hour or weekly limit. An account with no limit never brakes.

The retrospective reads this against the owner's 2026-11-01 17:56 CST ruling, "There is no usage limit" (decision `session-tiers`, the session roles). It reads that ruling as being about session length. That reading is the retrospective's, not the owner's.

Open question for the owner: does the no-limit ruling conflict with the brake reading? Open as owner page item 540 (usage-brake).

## Open question 14.Q2

Question 14.Q2, still open with the owner: where the brake lives. The two options are a statusline mod or `hooks/guard.py`.

## Before any build

The first step is a lane measurement: can a hook read the usage percentages? Unmeasured on most surfaces.

What main has. Measured on origin/main 7639443c62, all tracked files, for `rateLimits`, `percentUsed`, `five_hour` and `seven_day`:

- One reader: the desktop status line mod, `mods/desktop-statusline/hooks/register.tsx`. Its `refresh` reads `$.session.usage()` (line 113) and maps `usage.rateLimits` to `percentUsed` (lines 144 to 146). If `isOnDesktop` does not hold, it returns early (line 110). It reads on the desktop surface only.
- Its warnings fire at 80% and 95% (`WARN_AT`, line 16). They do not fire at 90%, 93% or 97%.
- Two other mods call `$.session.usage()` for context fill, not rate limits: `mods/session-board/hooks/register.mjs` (line 358) and `mods/token-weather/hooks/token-weather.mjs` (line 60).
- `mods/desktop-statusline/desktop-statusline.test.mjs` mocks an empty `rateLimits` list. It reads no percentage.

Unmeasured: whether a cloud session or a terminal hook can read the percentages.

Unmeasured: where the host gets the percentages. The value comes through the engine's `$.session.usage()`. This repo does not show its source.

The code home is open with question 14.Q2. The first lane names it after the measurement.

## Handoff case

Rulings go to a tracked home at once (decision `precompact-handoff`, item 5). This record is the tracked home for the usage brake ruling.

No guard on main refuses a ruling kept only in a handoff. The nearest guards, `handoff-sections` and `handoff-checked-stamp` in `hooks/guard.py`, check section names and premise stamps. <!-- glossary-ok: the guard's fixed rule id, as hooks/guard.py names it -->

## When this record changes

This record changes when the first lane measures whether a hook can read the usage percentages on each surface. It also changes when the owner corrects the scope reading or answers question 14.Q2.

Kind: build
Plan: docs/decisions/usage-brake.md#the-ruling (all)
Home: not set (question 14.Q2)
