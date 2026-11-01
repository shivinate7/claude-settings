# Design skills on screens

## The ruling

Owner, 2026-10-10: three third-party skills apply to any repo with screens. Each one is global and pinned. The procedure is in
`skills/design-review/SKILL.md`, the builder line in `agents/builder.md`, the designer steps in `agents/designer.md`, the reviewer clause in `agents/reviewer.md`.

- `frontend-design`: a builder loads it by name before it writes styling for a new screen, or in a repo with no design yet. A designer loads it
  by name before it draws (owner, 2026-10-30, waiting-page item 82 b, designer skills).
- Vercel `web-design-guidelines`: no plugin. A blind reviewer checks the changed pages against the rules at a pinned URL, after the build.
- `impeccable`: a pinned copy of its skill folder in `skills/impeccable`. No plugin. A second blind reviewer runs `/impeccable audit` and
  `/impeccable critique` only. A designer also runs `critique <mockup path>` on its own mockup before hand-off, and fixes each finding
  inside its write scope (owner, 2026-10-30, waiting-page item 82 b, designer skills). That pass is not the design review.
- Pins: Renovate moves each pin. `renovate.json` opens a draft PR each month and waits 14 days after a release
  (`minimumReleaseAge`). The owner merges or skips each PR. The pin homes are the `skill-v*` tag in `skills/impeccable/SOURCE.txt`, the
  commit in the Vercel URL in `skills/design-review/SKILL.md`, and the `anthropics/claude-code` ref in `settings.json`.
- Narrowing of `verification-newest-that-passes`: these three sources take the newest release only after it has waited 14 days. The owner
  wants their improvements.
- No Vercel plugin: the upstream skill fetches from `main` on every run, so a plugin update would move the rules without a decision. No
  impeccable plugin: it installs hooks that run `impeccable hook` on SessionStart, PostToolUse and Stop in every session, and an agent with
  Write and Edit. The guard sees neither.
- STE lint skips `skills/impeccable/`: it is third-party prose (Apache 2.0), and third-party skills need not follow our STE rules (owner,
  2026-10-10). Nobody edits the copy by hand.
- Guard rule `impeccable-review-only` (`hooks/guard.py`): the Skill tool loads impeccable only for `audit` or `critique`. In the shell,
  an impeccable call passes only for `detect ...` and `hooks status`. Every other subcommand is refused, also a later one. `detect` may
  download the engine, and it checks the engine against the committed checksum list `scripts/engine-checksums.txt` (owner, 2026-10-10).
- Guard rule `debug-port-ask` (`hooks/guard.py`): a shell command that launches an app with `--remote-debugging-port` (equals or space form),
  or sets `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` to a value that holds it, asks. A chained form denies as `ask-alone`. Text that only names
  the flag (`grep`, `echo`, `git commit -m`, `cat`) and `impeccable detect --cdp` pass. Risk kind: likely risk (coordinator ruling,
  2026-11-01, `building-port-keeps-behaviour`). Impeccable 4.8.0 `reference/critique.md` step 1 and `reference/audit.md` "Desktop apps"
  tell an agent to open a debug port, and main opened none without the owner. Landed 2026-11-01.
- Blind, then compare: each design reviewer judges the rendered screens before it reads the repo's design spec, tokens or design
  decisions. The orchestrator reads those only after both findings exist. Findings on the changed pages are not limited to the diff
  (`agents/reviewer.md`). A finding that agrees with the repo, or is a plain defect (accessibility, broken layout, overflow), is fixed
  before merge. A finding that clashes with the repo's design is never fixed and never dropped by a reviewer. It goes to the owner, one
  list per repo, with what the skill wants, what the repo has, and a recommendation.

Reason: the owner wants the skills to improve every repo. Conformity would make them worthless, so a repo does not silence a skill, and a
skill does not restyle a repo on its own. Pinning keeps an update from changing a look by itself. Reopen when a clash repeats across repos, or a skill restyles a repo. Then follow `outcomes-stale-decision-protocol`.

Kind: process
Home: skills/impeccable/SOURCE.txt
