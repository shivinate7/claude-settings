# Design skills on screens

## Ruling

Owner ruling, 2026-10-10. Three third-party skills apply to any repo with screens. Each one is
global and pinned.

- `frontend-design`: a builder loads it by name before it writes styling for a new screen, or
  in a repo with no design yet. It sets type, color and layout first.
- Vercel `web-design-guidelines`: no plugin. A blind reviewer checks the changed pages against
  the rules at a pinned URL, after the build.
- `impeccable`: a pinned copy of its skill folder in `skills/impeccable`. No plugin. A second
  blind reviewer runs `/impeccable audit` and `/impeccable critique` only.

The procedure is in `skills/design-review/SKILL.md`. The builder line is in `agents/builder.md`.
The reviewer clause is in `agents/reviewer.md`.

## Pins

- The impeccable pin is the tag on the pinned-source line in `skills/design-review/SKILL.md`.
  This record does not copy it. Moving the pin is a hand edit of that line and of the copy in
  `skills/impeccable`.
- The Vercel rules pin is a URL in `skills/design-review/SKILL.md`. Moving the pin is a hand
  edit of that URL.
- Why no Vercel plugin: the upstream skill fetches from `main` on every run. A plugin update
  would move the rules without a decision.
- Why no impeccable plugin, measured by review: the plugin installs hooks that run
  `impeccable hook` on SessionStart, PostToolUse and Stop in every session. It also installs an
  agent with Write and Edit. The guard sees neither.

Dated by: the impeccable pin and the Vercel URL in `skills/design-review/SKILL.md`, and the
guard rule.
A change to any of them means that this record is read again.

## Guard rule: impeccable-review-only

Owner ruling 2026-10-10 keeps this rule on the copy. It lets impeccable load only for `audit` or
`critique`. It refuses the other commands and the settings writers: `hooks on`, `install`,
`update`, `link`, `ignores`, `pin`, `doctor auto`, and any version spec.

Status: built in `hooks/guard.py` and routed in `settings.json`.
- Built and tested: the Skill tool, for any command except `audit` and `critique`. Shell
  `hooks` and `doctor auto`.
- Not built: shell `install`, `update`, `link`, `ignores`, `pin`, and any version spec.

Trust each part only after it goes red on its command (verification-trust-guard-after-red: a
guard is trusted once it goes red).

## Outcome protected

The owner wants the skills to improve every repo. Conformity would make them worthless. So a
repo does not silence a skill, and a skill does not restyle a repo on its own. Pinning keeps a
skill update from changing a look by itself.

## Blind, then compare

Each design reviewer judges the rendered screens before it reads the repo's design spec,
tokens or design decisions. The orchestrator reads those only after both findings exist.

Design-review findings on the changed pages are not limited to the diff (`agents/reviewer.md`).
So a reviewer may report older defects on those pages.

- Agrees with the repo, or is a plain defect (accessibility, broken layout, overflow): fixed
  before merge.
- Clashes with the repo's design: a reviewer never fixes it and never drops it. It goes to the
  owner, one list per repo, with what the skill wants, what the repo has, and a recommendation.

## Reopen

Reopen when a clash repeats across repos, or a skill restyles a repo. Then follow
outcomes-stale-decision-protocol: name the sentence, measure the claim, name the outcome it
protects, propose a fix, and wait for the owner.
