---
name: design-review
description: Use after a change to a screen in a repo that has screens. Runs two blind design reviews of the changed pages, then compares them with the repo's design records. Not for a change that has no screen.
---

Run this in the orchestrator. Workers never spawn, so the orchestrator spawns both reviewers.
Each skill runs at its pin in `settings.json`. The ruling is the design-skills record, 2026-10-10.

## Procedure

1. **List the changed pages.** Name each changed page and route. Capture a screenshot of each
   one at every size and theme it ships in.
2. **Spawn two blind reviewers.** Each brief names only the changed pages, routes and
   screenshots. Never give a reviewer the repo's design spec, tokens or design decisions.
   - Reviewer A loads Vercel `web-design-guidelines` and runs it on the changed pages.
   - Reviewer B runs `/impeccable audit` and `/impeccable critique` only. It never runs
     impeccable's build commands.
3. **Compare.** When both reports return, read the repo's design spec, tokens and design
   decisions. Set each finding against them.
4. **Sort each finding.**
   - Agrees with the repo, or is a plain defect (accessibility, broken layout, overflow): fix
     before merge. The reviewers never fix. Send the fix to the builder.
   - Clashes with the repo's design: never fix it, never drop it. Add it to the owner's list for
     that repo.
5. **Send the owner one list per repo.** Give each clash three parts: what the skill wants,
   what the repo has, and a recommendation.
6. **Verdict.** Give a verdict per screen at each size and theme
   (verification-screens-verdict: a verdict per screen, never a description).

## Rules

- No conformity either way. The repo does not silence a skill. A skill does not restyle the
  repo on its own.
- A skill update does not change a look by itself. Each skill stays at its pin.
