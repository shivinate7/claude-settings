---
name: design-review
description: Use after a change to a screen in a repo that has screens. Runs two blind design reviews of the changed pages, then compares them with the repo's design records. Not for a change that has no screen.
---

Run this in the orchestrator. Agents never spawn, so the orchestrator spawns both reviewers.
The ruling is decision design-skills (third-party design skills), 2026-10-10.

## Pinned sources

- Vercel rules: `https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/434b7f91364665f2f733b310ec54809bf8f37937/command.md`.
  The commit in the URL is the pin. Renovate proposes each move (decision design-skills, the
  third-party skill rulings).
  The upstream skill fetches from `main` on every run, so there is no plugin.
- impeccable: a pinned copy of `pbakaus/impeccable` `plugin/skills/impeccable` at tag
  `skill-v4.5.2` (Apache 2.0), in `skills/impeccable`. No plugin. Renovate proposes each move of
  the tag, and the `impeccable-sync` workflow replaces the copy with it. Guard rule
  `impeccable-review-only` lets it load only for `audit` or `critique` (decision design-skills,
  the impeccable ruling).

## Procedure

1. **List the changed pages.** Name each changed page and route. Capture a screenshot of each
   one at every size and theme it ships in. Use a headless or isolated browser. If a
   page needs the owner's login, use it; otherwise use none
   (`verification-browser-login-only-needed`). Before a window or a screen capture lands on the
   owner's screen, say so in one line (`verification-announce-own-screen`).
2. **Spawn two blind reviewers.** Each brief names only the changed pages, routes and
   screenshots, plus the reviewer's own instructions below. Never give a reviewer the repo's
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
   changed pages, the screenshots, the step's mockup in the design folder, and the full list. It
   judges each screen against the mockup and the repo's design rules, and sets each finding
   against them. Do not change the list. The design reviewer is not blind, so it never takes the
   place of Reviewer A or B.
5. **Sort each finding.**
   - Agrees with the repo, or is a plain defect (accessibility, broken layout, overflow): fix
     before merge. The reviewers never fix. Send the fix to the builder.
   - Clashes with the repo's design: never fix it, never drop it. Add it to the owner's list for
     that repo.
6. **Send the owner one list per repo.** Give each clash three parts: what the skill wants,
   what the repo has, and a recommendation.
7. **Verdict.** Give a verdict per screen at each size and theme
   (verification-screens-verdict: a verdict per screen, never a description). A screen that did
   not render, or has no screenshot, gets `unknown`, never pass or fail
   (`verification-report-unknown-reads`).

## Rules

- No conformity either way. The repo does not silence a skill. A skill does not restyle the
  repo on its own.
- A skill update does not change a look by itself. Each source stays at its pin.
- A change gets at most three review rounds (`roles-review-cap-three`). A change that only
  deletes and adds nothing gets one round. A round is steps 2 to
  5, with a new pair of blind reviewers. After round 3, run no fourth round. Each finding that
  is still open becomes a debt if Claude is likely to hit it in normal work. Otherwise it becomes a
  note. Each points to its decision (`roles-review-cap-three`, `roles-holes-are-debts`).
- House rules (decision ux-house-rules, the UX rules for builders and reviewers): a builder reads `~/.claude/docs/design/principles.md` before it writes UI. Reviewer A's brief asks for the house checklist (step 2). House design values: `~/.claude/docs/design/tokens.md`.
- Layout and spacing: Reviewer A's house checklist covers the rules in `~/.claude/docs/design/layout.md` (gap on the parent, layout primitives, container queries, fluid tokens).
