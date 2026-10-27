---
name: design-explore
description: Use before the builder on a lane that explores a screen, a new screen or a redesign. Spawns designer lanes in blind, informed and directed kinds, so the owner can cull a varied set of mockups. Not for a small change to an existing screen.
---

Run this in the orchestrator. Workers never spawn, so the orchestrator spawns every designer lane.
The ruling is decision design-agents, 2026-10-27. The owner wants a mix of control and new ideas
between the mockups.

## Lane kinds

Each lane is one designer agent: agentType `designer`, Opus (`subagent-model-cap`), in its own
worktree (`parallelism-each-own-checkout`).

- **Blind lane.** The brief names only the screen's job, its users, its data shapes and the house
  rules in `~/.claude/ux/`. The brief never gives the current screen, its code, its screenshots, its
  mockups, or the repo's design spec and tokens. A blind lane shows ideas the repo's habits would
  hide.
- **Informed lane.** The brief gives the current screen, its mockups, the spec and the tokens.
- **Directed lane.** An informed lane plus one named direction, such as denser, phone first, or one
  primary action. The orchestrator picks directions that differ from each other.

## Default mix

Per screen: two blind lanes, one informed lane, two directed lanes. The mix is a default. A brief or
the owner may change it. A small change to an existing screen skips this skill and gets one informed
designer.

## Procedure

1. **Write the briefs.** Use the lane kinds above. Name the lane kind in each brief, and the
   direction for a directed lane. Point the brief at files; never paste them
   (`tokens-point-brief-at-files`).
2. **Name the files.** Each lane writes `<screen>-<kind>-<n>.html` and
   `<screen>-<kind>-<n>-notes.md` in the design folder. `<kind>` is `blind`, `informed` or
   `directed`. `<n>` counts the lanes of that kind, from 1. So lanes never collide. Each mockup
   prints its lane kind on the page. A directed mockup also prints its direction.
3. **Spawn all lanes together.** The lanes share no input, so they run in parallel. Lanes never talk
   to each other (`parallelism-no-mid-task-talk`).
4. **Collect.** Read each report, never a transcript. Give the owner one list: each mockup with its
   path, kind and direction.
5. **The owner culls** from the whole set. The kept mockup becomes the step's mockup, the one the
   builder builds to (`agents/builder.md`). The orchestrator removes the other mockups and notes in
   a PR. Git keeps them.

## Rules

- A blind brief that names the current screen, its code, a mockup, the spec or the tokens is a
  defect. Re-brief the lane.
- The designer lane writes only in the design folder (guard rule `designer-scope`).
- After the cull, the builder and the design reviewer run as usual (decision design-agents).
