# Design skills on screens

## Ruling

Owner ruling, 2026-10-10. Three third-party skills apply to any repo with screens. Each skill
is global and version-pinned.

- `frontend-design`: a builder loads it by name before it writes styling for a new screen, or
  in a repo with no design yet. It sets type, color and layout first.
- Vercel `web-design-guidelines`: a blind reviewer runs it on the changed pages after the build.
- `impeccable`: a second blind reviewer runs `/impeccable audit` and `/impeccable critique`
  only. It never runs impeccable's build commands.

The procedure is in `skills/design-review/SKILL.md`. The builder line is in `agents/builder.md`.
The reviewer line is in `agents/reviewer.md`.

## Outcome protected

The owner wants the skills to improve every repo. Conformity would make them worthless. So a
repo does not silence a skill, and a skill does not restyle a repo on its own. Pinning keeps a
skill update from changing a look by itself.

## Blind, then compare

Each design reviewer judges the rendered screens before it reads the repo's design spec,
tokens or design decisions. The orchestrator reads those only after both findings exist.

- Agrees with the repo, or is a plain defect (accessibility, broken layout, overflow): fixed
  before merge.
- Clashes with the repo's design: a reviewer never fixes it and never drops it. It goes to the
  owner, one list per repo, with what the skill wants, what the repo has, and a recommendation.

## Pins

The pins live in `settings.json`, in `enabledPlugins` and `extraKnownMarketplaces`. This record
does not copy them. Open: no pin is set yet for Vercel `web-design-guidelines`.

Dated by: the pins in `settings.json`. A pin change, or a new owner ruling, means that this
record is read again.

## Reopen

Reopen when a clash repeats across repos, or a skill restyles a repo. Then follow
outcomes-stale-decision-protocol: name the sentence, measure the claim, name the outcome it
protects, propose a fix, and wait for the owner.
