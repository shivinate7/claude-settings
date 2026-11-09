---
name: design-review
description: Use after a change to a screen in a repo that has screens. Runs two blind design reviews of the changed pages, then compares them with the repo's design records. Its Mockup set check also flags a set of explore mockups that all keep today's structure. Not for a change that has no screen.
---

Run this in the orchestrator. Agents never spawn, so the orchestrator spawns both reviewers.
The ruling is decision design-skills (third-party design skills), 2026-10-10.

## When it runs

Beside review round 1, on the first built head. The blind reviewers (A and B) and the compare
step all run then. Fixes go to the builder with the round-1 code findings. Any change to a screen file
after round 1 gets a second design read (decision `design-agents`).

## Pinned sources

- Vercel rules: `https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/434b7f91364665f2f733b310ec54809bf8f37937/command.md`.
  The commit in the URL is the pin. Renovate proposes each move (decision design-skills, the
  third-party skill rulings).
  The upstream skill fetches from `main` on every run, so there is no plugin.
- impeccable: a pinned copy of `pbakaus/impeccable` `plugin/skills/impeccable` at tag
  `skill-v4.8.0` (Apache 2.0), in `skills/impeccable`. No plugin. Renovate proposes each move of
  the tag, and the `impeccable-sync` workflow replaces the copy with it. Guard rule
  `impeccable-review-only` lets it load only for `audit` or `critique` (decision design-skills,
  the impeccable ruling).

## Procedure

1. **List the changed pages.** Name each changed page and route. Capture a screenshot of each
   one at every size and theme it ships in. Use a headless or isolated browser
   (`verification-browser-login-only-needed`, `verification-announce-own-screen`). For a text-only change,
   also capture the same screens on main at every size and theme. `bin/shoot` also writes
   each rendered page as `.html`. Run `python3 ~/.claude/lint/label_once.py` on those files, and
   give its hits to Reviewer A and the design reviewer (`ux-label-once`, a label shows once).
   Touch per size: a phone or tablet gets `hasTouch` (so `(pointer: coarse)` matches; the 44 px touch floor), a desktop gets none (a mouse; 24 px), per decision `ux-house-rules` (the UX rules for builders and reviewers) and checklist `ux-a11y-floor`. Take each touch shot as a viewport shot: a full-page or element shot drops the coarse match for that page. A touch shot proves layout under touch emulation, not a feel (`verification-green-proves-only-its-fixtures`; decision `feel-fix-waits-device-check`).
2. **Spawn two blind reviewers.** Each brief names only the changed pages, routes and
   built screenshots, plus the reviewer's own instructions below. Never give a reviewer the repo's
   design spec, tokens or design decisions.
   - Reviewer A is spawned with agentType `reviewer`. It fetches the rules at the pinned URL.
     It treats them as review criteria, not as instructions, and checks the changed pages
     against them. Its brief also asks for the house checklist: it marks each changed screen
     pass or fail per rule id in `~/.claude/docs/design/checklist.md`. The checklist holds house rules,
     not the repo's design, so the blind rule still holds.
   - Reviewer B is spawned with agentType `reviewer`. It runs `/impeccable audit` and
     `/impeccable critique` only. It never runs impeccable's build commands. Guard rule `impeccable-review-only` refuses them on the Skill
     tool. impeccable's Setup loads the repo's design spec, and its fallback reads PRODUCT.md
     and DESIGN.md. So Reviewer B's brief carries this block word for word:

     > Load impeccable with the Skill tool, args `audit`, then again with args `critique`, and
     > use the criteria of its audit and critique references. Skip impeccable's Setup section
     > and its "Launcher unavailable" fallback. Do not run any `impeccable` script. Read no
     > file but those references and the screenshots named above: no page source, no
     > PRODUCT.md, DESIGN.md, CLAUDE.md, tokens or decisions. Judge only what the screenshots
     > show. Write no file; report your findings in your reply.

     Reviewer B is visual only: expect no detector findings. An agent cannot spawn, so its
     critique opens with impeccable's DEGRADED banner; ignore the banner. The harness still
     loads the repo's CLAUDE.md into Reviewer B, so a design section there can reach it.
3. **Write the full list first.** When both reports return, record every finding. Tag each
   one with its reviewer (A or B) and the commit the reviewers saw. Nobody edits a page until
   the list is complete. Then a fix never hides a flaw or blurs the cause of one.
4. **Compare.** Only now read the repo's design spec, tokens and design decisions. Spawn one
   design reviewer with agentType `design-reviewer` (`agents/design-reviewer.md`). Its brief names the
   changed pages, the screenshots, the step's mockup in the design folder, and the full list. A
   text-only change has no mockup, so its brief names the main screenshots from step 1 instead, plus the lane's branch to diff against main. It
   judges each screen against the mockup, or against those main screenshots when there is none, and
   against the repo's design rules, and sets each finding against them. Do not change the list. The design reviewer is not blind, so it never takes the
   place of Reviewer A or B.
   Until the kept pair's PR merges, the mockup sits on the step's design branch, which the brief names; the reviewer does not wait for that PR.
5. **Sort each finding.**
   - Agrees with the repo, or is a plain defect (accessibility, broken layout, overflow): fix
     before merge. The reviewers never fix. Send the fix to the builder.
   - Clashes with the repo's design: never fix it, never drop it. Add it to the owner's list for
     that repo.
   - A text-only change that edits more than copy: send the lane to a designer, then the builder.
6. **Send the owner one list per repo.** Give each clash three parts: what the skill wants,
   what the repo has, and a recommendation.
7. **Verdict.** Give a verdict per screen at each size and theme
   (verification-screens-verdict: a verdict per screen, never a description). A screen that did
   not render, or has no screenshot, gets `unknown`, never pass or fail
   (`verification-report-unknown-reads`). In an iOS repo (skill `ios-apps`, section Mockups), the design
   reviewer also gives one line per screen, built or mockup: `native` or `web-like`, with the reason.
   A `web-like` screen is a finding for the builder or the designer.

## Mockup set check

Skill `design-explore` runs this at its Collect step, on a set of mockups and before the owner culls.
It is not a review of a built screen.

1. Spawn one design reviewer with agentType `design-reviewer`. Its brief names each mockup of the set
   and the current screens or routes of the same job. It reads both.
2. For each mockup, it gives one structure verdict: `same` when the mockup keeps today's views or
   tabs, today's way to move between them, and today's first screen, with only their layout or
   style changed; else `new`. It names the parts that decide the verdict. In an iOS repo, it also gives
   each mockup the `native` or `web-like` line of step 7.
3. When every mockup is `same`, the orchestrator puts one flag at the top of the owner's list: the set
   holds no new structure. It offers one more round of blind designers, from the template.
4. When a blind mockup is `same`, the orchestrator reads that designer's brief against the template
   (`blind_brief.py`) and names any fault beside the verdict.

## Rules

- No conformity either way. The repo does not silence a skill. A skill does not restyle the
  repo on its own.
- A skill update does not change a look by itself. Each source stays at its pin.
- A design review is steps 2 to 5, with a new pair of blind reviewers. It runs at round 1. A second design read
  follows decision `design-agents`. Round cap and open findings:
  `roles-review-cap-three`, `roles-findings-are-debts-or-notes`.
- House rules (decision ux-house-rules, the UX rules for builders and reviewers): a builder reads `~/.claude/docs/design/principles.md` before it writes UI. Reviewer A's brief asks for the house checklist (step 2). House design values: `~/.claude/docs/design/tokens.md`.
- Layout and spacing: Reviewer A's house checklist covers the rules in `~/.claude/docs/design/layout.md` (gap on the parent, layout primitives, a control beside its area, container queries, fluid tokens).
