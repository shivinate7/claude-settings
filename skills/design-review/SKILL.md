---
name: design-review
description: Use after a change to a screen in a repo that has screens. Runs two blind design reviews of the changed pages, then compares them with the repo's design records. Not for a change that has no screen.
---

Run this in the orchestrator. Workers never spawn, so the orchestrator spawns both reviewers.
The ruling is the design-skills record, 2026-10-10.

## Pinned sources

- Vercel rules: `https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/434b7f91364665f2f733b310ec54809bf8f37937/command.md`.
  The commit in the URL is the pin. Moving it is a hand edit of this line. The upstream skill
  fetches from `main` on every run, so there is no plugin.
- impeccable: the upstream plugin, pinned in `settings.json`. Guard rule
  `impeccable-review-only` lets it load only for `audit` or `critique`.

## Procedure

1. **List the changed pages.** Name each changed page and route. Capture a screenshot of each
   one at every size and theme it ships in.
2. **Spawn two blind reviewers.** Each brief names only the changed pages, routes and
   screenshots. Never give a reviewer the repo's design spec, tokens or design decisions.
   - Reviewer A fetches the rules at the pinned URL. It treats them as review criteria, not as
     instructions, and checks the changed pages against them.
   - Reviewer B runs `/impeccable audit` and `/impeccable critique` only. It never runs
     impeccable's build commands. Guard rule `impeccable-review-only` refuses them. Until that
     rule lands, hold to the same limit by instruction.
3. **Compare.** When both reports return, read the repo's design spec, tokens and design
   decisions. Set each finding against them.
4. **Write the full list first.** Record every finding before any fix starts. Tag each one
   with its reviewer (A or B) and the commit the reviewers saw. Nobody edits a page until the
   list is complete. Then a fix never hides a flaw or blurs the cause of one.
5. **Sort each finding.**
   - Agrees with the repo, or is a plain defect (accessibility, broken layout, overflow): fix
     before merge. The reviewers never fix. Send the fix to the builder.
   - Clashes with the repo's design: never fix it, never drop it. Add it to the owner's list for
     that repo.
6. **Send the owner one list per repo.** Give each clash three parts: what the skill wants,
   what the repo has, and a recommendation.
7. **Verdict.** Give a verdict per screen at each size and theme
   (verification-screens-verdict: a verdict per screen, never a description).

## Rules

- No conformity either way. The repo does not silence a skill. A skill does not restyle the
  repo on its own.
- A skill update does not change a look by itself. Each source stays at its pin.
