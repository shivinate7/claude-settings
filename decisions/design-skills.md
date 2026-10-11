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

Renovate moves each pin. The owner installs the Renovate GitHub app under their login. A
`renovate.json` in this repo tracks the three pins below. It opens a draft PR each month, with
release notes, and waits 14 days after a release (`minimumReleaseAge`). The owner merges or
skips each PR.

- impeccable: the `skill-v*` tag in `skills/impeccable/SOURCE.txt` and the pinned-source line in
  `skills/design-review/SKILL.md`. This record does not copy it. Renovate edits the tag. The
  `impeccable-sync` workflow copies the folder at the new tag into the Renovate branch.
- Vercel rules: the commit in the URL in `skills/design-review/SKILL.md`.
- frontend-design: the `anthropics/claude-code` ref in `settings.json`.
- Exception to `verification-bump-first-fix-version` (bump to the first fixing version): these
  three sources bump to the newest release that has waited 14 days. The owner wants their
  improvements, so the first fix is not the target.
- Why no Vercel plugin: the upstream skill fetches from `main` on every run. A plugin update
  would move the rules without a decision.
- Why no impeccable plugin, measured by review: the plugin installs hooks that run
  `impeccable hook` on SessionStart, PostToolUse and Stop in every session. It also installs an
  agent with Write and Edit. The guard sees neither.

Dated by: the three pins and the guard rule.
A change to any of them means that this record is read again.

## Guard rule: impeccable-review-only

Owner ruling 2026-10-10 keeps this rule on the copy. It lets impeccable load only for `audit` or
`critique`. It refuses the other commands and the settings writers: `hooks on`, `install`,
`update`, `link`, `ignores`, `pin`, `doctor auto`, and any version spec.

Status: built in `hooks/guard.py` and routed in `settings.json`.
- Skill tool: any command except `audit` and `critique` is refused. The name `/impeccable` counts.
- Shell: `hooks` (except `hooks status`), `install`, `update`, `link`, `ignores`, `pin` and
  `doctor auto` are refused. The package name is read without `@version`, through `npx -y` and
  `npx -p <spec> impeccable`.
- Limit: `audit then polish` is allowed. The argument-hint says the second word is a target.

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
