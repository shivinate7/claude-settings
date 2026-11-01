# Design skills on screens

## The ruling

Owner, 2026-10-10: three third-party skills apply to any repo with screens. Each one is global and pinned. The owner ruled that
`frontend-design` floats on `claude-plugins-official` main (2026-11-01 11:43 CST, waiting-page item 120, pick c, frontend-design pin). The
float is not live while the `claude-code-plugins` ref is held at v2.1.311 (`settings.json`): at that tag the plugin comes from
`./plugins/frontend-design` inside the tag. The procedure is in `skills/design-review/SKILL.md`, the builder line in `agents/builder.md`, the designer steps in `agents/designer.md`, the
reviewer clause in `agents/reviewer.md`.

- `frontend-design`: a builder loads it by name before it writes styling for a new screen, or in a repo with no design yet. A designer loads it
  by name before it draws (owner, 2026-10-30, waiting-page item 82 b, designer skills). At claude-code v2.1.312, v2.1.314
  and v2.1.316 the `claude-code-plugins` marketplace lists it as a git-subdir of `anthropics/claude-plugins-official` at ref `main` (review
  round 1 of lane fd-float-cc-newest read `marketplace.json` at these tags and at v2.1.311). A fresh headless start auto-installed it on 0 of
  8 starts, measured at v2.1.312 and v2.1.316 (v2.1.313 to v2.1.315 not started). It installed on 1 of 2 starts at v2.1.311 (review of lane
  fd-float-cc-newest, 2026-11-01). `claude plugin install` works at v2.1.316. The ref stays held at v2.1.311 until a fresh start on a newer
  tag installs it.
- Vercel `web-design-guidelines`: no plugin. A blind reviewer checks the changed pages against the rules at a pinned URL, after the build.
- `impeccable`: a pinned copy of its skill folder in `skills/impeccable`. No plugin. A second blind reviewer runs `/impeccable audit` and
  `/impeccable critique` only. A designer also runs `critique <mockup path>` on its own mockup before hand-off, and fixes each finding
  inside its write scope (owner, 2026-10-30, waiting-page item 82 b, designer skills). That pass is not the design review.
- Pins: Renovate moves each pin. `renovate.json` opens a draft PR each month. The owner merges or skips each PR. The pin homes are the `skill-v*` tag in `skills/impeccable/SOURCE.txt`, the
  commit in the Vercel URL in `skills/design-review/SKILL.md`, and the `anthropics/claude-code` ref in `settings.json`. Each pin moves to the
  newest version that passes its checks (`verification-newest-that-passes`). The `claude-code` ref is the one that carries `frontend-design`.
- Narrowing of `verification-newest-that-passes`: the impeccable and `claude-code` pins take the newest release only after it has waited 14
  days (`minimumReleaseAge`, global in `renovate.json`). The Vercel pin's wait is unknown: its `git-refs` source has no release time, and
  `renovate.json` sets `timestamp-optional` for it. The owner wants their improvements.
- No Vercel plugin: the upstream skill fetches from `main` on every run, so a plugin update would move the rules without a decision. No
  impeccable plugin: it installs hooks that run `impeccable hook` on SessionStart, PostToolUse and Stop in every session, and an agent with
  Write and Edit. The guard sees neither.
- STE lint skips `skills/impeccable/`: it is third-party prose (Apache 2.0), and third-party skills need not follow our STE rules (owner,
  2026-10-10). Nobody edits the copy by hand.
- Guard rule `impeccable-review-only` (`hooks/guard.py`): the Skill tool loads impeccable only for `audit` or `critique`. In the shell,
  an impeccable call passes only for `detect ...` and `hooks status`. Every other subcommand is refused, also a later one. `detect` may
  download the engine, and it checks the engine against the committed checksum list `scripts/engine-checksums.txt` (owner, 2026-10-10).
- Owner ruling, waiting-page item 119 (impeccable debug port), pick b, 2026-11-01 11:43 CST: take impeccable 4.8.0 as is, with no guard. The guard does not ask on it. The owner asked how the port avoids a clash; the next line answers.
  Launch headless Chrome with `--remote-debugging-port=0`. Measured (lane drop-debug-port-ask, 2026-11-01): the OS gave a free port (43677), written as the first line of `DevToolsActivePort` in its `--user-data-dir`; `impeccable detect --cdp 43677` ran. Electron, and WebView2 with `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS="--remote-debugging-port=0"`: unmeasured. The skill's reference/critique.md and reference/audit.md name 9222 as an example; `detect --cdp` takes any port.
- Blind, then compare: each design reviewer judges the rendered screens before it reads the repo's design spec, tokens or design
  decisions. The orchestrator reads those only after both findings exist. Findings on the changed pages are not limited to the diff
  (`agents/reviewer.md`). A finding that agrees with the repo, or is a plain defect (accessibility, broken layout, overflow), is fixed
  before merge. A finding that clashes with the repo's design is never fixed and never dropped by a reviewer. It goes to the owner, one
  list per repo, with what the skill wants, what the repo has, and a recommendation.

Reason: the owner wants the skills to improve every repo. Conformity would make them worthless, so a repo does not silence a skill, and a
skill does not restyle a repo on its own. Pinning impeccable and Vercel keeps an update from changing a look by itself. The `frontend-design` ref moves only when a newer tag installs it at a fresh start. Reopen when a clash repeats across repos, or a skill restyles a repo. Then follow `outcomes-stale-decision-protocol`.

Kind: process
Home: skills/impeccable/SOURCE.txt
