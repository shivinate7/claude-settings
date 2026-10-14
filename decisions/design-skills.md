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
- STE lint skips `skills/impeccable/`. It is third-party prose (Apache 2.0), and the owner ruled
  on 2026-10-10 that third-party skills need not follow our STE rules. The repo's
  `.ste-lint-exclude` file holds the path. The local write hook `lint/ste_gate.py` has no
  exclude list, so it is unchanged. Nobody edits the copy by hand, so the hook never meets it.

Kind: process
Home: skills/impeccable/SOURCE.txt

Dated by: the three pins and the guard rule.
A change to any of them means that this record is read again.

## Guard rule: impeccable-review-only

Owner ruling 2026-10-10 keeps this rule on the copy. The Skill tool loads impeccable only for
`audit` or `critique`. The shell is an allow list: an impeccable call passes only for
`detect ...` and `hooks status`. Every other subcommand is refused, also a later one.

Status: built in `hooks/guard.py` and routed in `settings.json`.
- Skill tool: any command except `audit` and `critique` is refused. The name `/impeccable` counts.
- Shell: the package name is read without `@version`, path or suffix (`.cmd`, `.exe`). The rule
  reads through `npx -y`, `npx -p <spec> impeccable`, `npx -c`, `sh -c`, `bash -c` and
  PowerShell's call operator `&`.
- Limit: `audit then polish` is allowed. The argument-hint says the second word is a target.
- Limits, not read through: `pnpx`, `bun x`, `timeout N`, `cmd /c`, `powershell -Command`, npx
  with `--registry` or `--cache`, and `| sh`.
  A paren or an assignment with no space before the command also passes: `(impeccable install)`
  and `$r=& impeccable install`.
- Rare false alarms: `npm run impeccable -- detect` and `impeccable --json detect` are refused.
- Accepted: `detect` may download the engine. The owner accepted this on 2026-10-10, as
  joyous did. It trusts the release checksum.

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
