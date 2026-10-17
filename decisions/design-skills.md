# Design skills on screens

## Ruling

Owner, 2026-10-10: three third-party skills apply to any repo with screens. Each one is global and pinned.

- `frontend-design`: a builder loads it by name before it writes styling for a new screen, or in a repo with no design yet. It sets type, color and layout first.
- Vercel `web-design-guidelines`: no plugin. A blind reviewer checks the changed pages against the rules at a pinned URL, after the build.
- `impeccable`: a pinned copy of its skill folder in `skills/impeccable`. No plugin. A second blind reviewer runs `/impeccable audit` and `/impeccable critique` only.

The procedure is in `skills/design-review/SKILL.md`. The builder line is in `agents/builder.md`. The reviewer clause is in `agents/reviewer.md`.

Pins: Renovate moves each pin. `renovate.json` opens a draft PR each month, with release notes, and waits 14 days after a release (`minimumReleaseAge`). The owner merges or skips each PR.

- impeccable: the `skill-v*` tag in `skills/impeccable/SOURCE.txt` and the pinned-source line in `skills/design-review/SKILL.md`. The `impeccable-sync` workflow copies the folder at the new tag into the Renovate branch.
- Vercel rules: the commit in the URL in `skills/design-review/SKILL.md`.
- frontend-design: the `anthropics/claude-code` ref in `settings.json`.
- Exception to `verification-bump-first-fix-version` (bump to the first fixing version): these three sources bump to the newest release that has waited 14 days. The owner wants their improvements.
- Why no Vercel plugin: the upstream skill fetches from `main` on every run, so a plugin update would move the rules without a decision.
- Why no impeccable plugin: it installs hooks that run `impeccable hook` on SessionStart, PostToolUse and Stop in every session, and an agent with Write and Edit. The guard sees neither.
- STE lint skips `skills/impeccable/`: it is third-party prose (Apache 2.0), and third-party skills need not follow our STE rules (owner, 2026-10-10). The `.ste-lint-exclude` file holds the path. Nobody edits the copy by hand, so the write hook `lint/ste_gate.py` never meets it.

Guard rule `impeccable-review-only` (`hooks/guard.py`, routed in `settings.json`): the Skill tool loads impeccable only for `audit` or `critique`, and the name `/impeccable` counts. In the shell, an impeccable call passes only for `detect ...` and `hooks status`. Every other subcommand is refused, also a later one.

- The package name is read without `@version`, path or suffix (`.cmd`, `.exe`). The rule reads through `npx -y`, `npx -p <spec> impeccable`, `npx -c`, `sh -c`, `bash -c` and PowerShell's call operator `&`.
- Accepted: `detect` may download the engine, and it trusts the release checksum (owner, 2026-10-10).
- Limits: `audit then polish` is allowed. Not read through: `pnpx`, `bun x`, `timeout N`, `cmd /c`, `powershell -Command`, npx with `--registry` or `--cache`, `| sh`, `(impeccable install)` and `$r=& impeccable install`. Rare false alarms: `npm run impeccable -- detect` and `impeccable --json detect`.

Blind, then compare: each design reviewer judges the rendered screens before it reads the repo's design spec, tokens or design decisions. The orchestrator reads those only after both findings exist. Findings on the changed pages are not limited to the diff (`agents/reviewer.md`).

- A finding that agrees with the repo, or is a plain defect (accessibility, broken layout, overflow), is fixed before merge.
- A finding that clashes with the repo's design is never fixed and never dropped by a reviewer. It goes to the owner, one list per repo, with what the skill wants, what the repo has, and a recommendation.

Why: the owner wants the skills to improve every repo. Conformity would make them worthless, so a repo does not silence a skill, and a skill does not restyle a repo on its own. Pinning keeps an update from changing a look by itself.

Reopen when a clash repeats across repos, or a skill restyles a repo. Then follow `outcomes-stale-decision-protocol`.

Kind: process
Home: skills/impeccable/SOURCE.txt
