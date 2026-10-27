---
name: design-explore
description: Use before the builder on a lane that explores a screen, a new screen or a redesign. Spawns designer lanes in blind, informed and directed kinds, so the owner can cull a varied set of mockups. Not for a small change to an existing screen.
---

Run this in the orchestrator. Workers never spawn, so the orchestrator spawns every designer lane.
The ruling is decision design-agents, 2026-10-27. The owner wants a mix of control and new ideas
between the mockups.

## Lane kinds

Each lane is one designer agent: agentType `designer`, Opus (`agent-model-cap`), in its own
worktree (`parallelism-each-own-checkout`).

- **Blind lane.** The brief names only the screen's job, its users, its data shapes and the house
  rules in `~/.claude/docs/design/`. The brief never gives the current screen, its code, its screenshots, its
  mockups, or the repo's design spec and tokens. The orchestrator reads the data shapes from the spec's data section or
  the owner's words, and writes them into the brief in plain words. The brief never names the spec.
  Never paste screen code into a blind brief. A blind lane shows ideas the repo's habits would hide.
  It rests on its brief and its own instruction. Each designer's worktree holds the code, spec,
  tokens and mockups, and the guard `designer-scope` limits writes only, so nothing blocks the read.
- **Informed lane.** The brief gives the current screen, its mockups, the spec and the tokens.
- **Directed lane.** An informed lane plus one named direction, such as denser, phone first, or one
  primary action. The orchestrator picks directions that differ from each other.

## Default mix

Per screen: two blind lanes, one informed lane, two directed lanes. The mix is a default. A brief or
the owner may change it. A small change to an existing screen skips this skill and gets one informed
designer.

## Procedure

1. **Write the briefs.** Use the lane kinds above. The first line of each brief is
   `Lane kind: blind|informed|directed`. A directed brief adds its direction. The skill always names
   the kind; a designer reads a brief with no kind as informed. The brief gives the lane its `<n>`.
   A blind lane never reads other files in the design folder, sibling lane mockups included. Point the brief at files; never paste them
   (`tokens-point-brief-at-files`).
2. **Name the files.** Each lane writes `<screen>-<kind>-<n>.html` and
   `<screen>-<kind>-<n>-notes.md` in the design folder. `<kind>` is `blind`, `informed` or
   `directed`. `<n>` counts the lanes of that kind, from 1. The orchestrator assigns it in the brief. So lanes never collide. Each mockup
   prints its lane kind on the page. A directed mockup also prints its direction.
3. **Spawn all lanes together.** The lanes share no input, so they run in parallel. Lanes never talk
   to each other (`parallelism-no-mid-task-talk`).
4. **Collect.** Read each report, never a transcript. Give the owner one list: each mockup with its
   path, kind and direction.
5. **Gather.** Each lane pushes its own branch. The orchestrator copies every lane's pair onto the
   step's design branch, so the owner sees the whole set in one place.
6. **The owner culls** from the whole set. The orchestrator renames the kept pair to `<screen>.html`
   and `<screen>-notes.md`, and deletes the rest in the same branch. Git keeps them. It names the
   kept path in the briefs of the builder and the design reviewer, and the builder builds to it
   (`agents/builder.md`).
7. **Clean up.** Push each lane branch to `archive/<branch>`, then delete it locally
   (`shared-trees-archive-then-delete`).

## Rules

- A blind brief that names the current screen, its code, a mockup, the spec or the tokens is a
  defect. Re-brief the lane.
- The designer lane writes only in the design folder (guard rule `designer-scope`).
- After the cull, the builder and the design reviewer run as usual (decision design-agents).
