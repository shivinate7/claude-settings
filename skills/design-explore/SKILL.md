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

- **Blind lane.** Build the brief from the template `blind-brief.md` beside this file, and from
  nothing else. It holds the user's job in their own words, the things the job handles, the device
  and its poses, the brand palette, and fixed House rules and Deliver text. It never names the current
  screen, a view of today's product, its code, a screenshot, a mockup, a path or link, the spec, the
  tokens, or a keep or match rule. The orchestrator reads the job and the data from the spec or the
  owner's words, and writes them in plain words. A blind lane shows ideas the repo's habits would
  hide. Each designer's worktree holds the code, spec, tokens and mockups, and the guard
  `designer-scope` limits writes only, so the brief and the designer's own instruction keep it blind.
- **Informed lane.** The brief gives the current screen, its mockups, the spec and the tokens. Its
  second line is `Blind lanes: <n>`, the count of the run's blind lanes.
- **Directed lane.** An informed lane plus one named direction, such as denser, phone first, or one
  primary action. The orchestrator picks directions that differ from each other.

## Default mix

Per screen: two blind lanes, one informed lane, two directed lanes. The mix is a default. A brief or
the owner may change it, but a run keeps at least one blind lane unless the owner asks for none. Then
each informed and directed brief carries `Blind lanes: none, owner: "<the owner's words>"`. A small change to an existing screen skips this skill and gets one informed
designer.

## Procedure

1. **Write the briefs.** Use the lane kinds above. The first line of each brief is
   `Lane kind: blind|informed|directed`. A directed brief adds its direction. The skill always names
   the kind; a designer reads a brief with no kind as informed. The brief gives the lane its `<n>`.
   A blind lane never reads other files in the design folder, sibling lane mockups included. Point the brief at files; never paste them
   (`tokens-point-brief-at-files`). Write each brief to `<scratchpad>/design-explore/<screen>/<screen>-<kind>-<n>.md`.
2. **Check the briefs.** Run `python3 ~/.claude/hooks/blind_brief.py --run <that folder> --current <view>`,
   with one `--current` per view name of today's product that is not a plain word of the job, and
   `--owner-asked-none "<words>"` only when the owner asked for no blind lane. Exit 0 is clean. On
   exit 1, rewrite each brief it names and run it again. The same check runs at each designer spawn
   (hook `blind_brief.py`), but only this run sees the whole set and the view names.
3. **Name the files.** Each lane writes `<screen>-<kind>-<n>.html` and
   `<screen>-<kind>-<n>-notes.md` in the design folder. `<kind>` is `blind`, `informed` or
   `directed`. `<n>` counts the lanes of that kind, from 1. The orchestrator assigns it in the brief. So lanes never collide. Each mockup
   prints its lane kind on the page. A directed mockup also prints its direction.
4. **Spawn all lanes together.** The lanes share no input, so they run in parallel. Lanes never talk
   to each other (`parallelism-no-mid-task-talk`).
5. **Collect.** Read each report, never a transcript. Then run the structure check of skill
   `design-review` (Mockup set check) on the whole set. Give the owner one list: each mockup with its
   path, kind and direction, and the structure verdict of each.
6. **Gather.** Each lane pushes its own branch. The orchestrator copies every lane's pair onto the
   step's design branch, so the owner sees the whole set in one place.
7. **The owner culls** from the whole set. The orchestrator renames the kept pair to `<screen>.html`
   and `<screen>-notes.md`, and deletes the rest in the same branch. Git keeps them. It names the
   kept path in the briefs of the builder and the design reviewer, and the builder builds to it
   (`agents/builder.md`).
8. **Clean up.** Push each lane branch to `archive/<branch>`, then delete it locally
   (`shared-trees-archive-then-delete`).

## Rules

- A blind brief that leaves the template, or names the current screen, its code, a mockup, the spec,
  the tokens or a keep or match rule, is a defect. The hook `blind_brief.py` refuses the spawn
  (decision blind-briefs-use-a-template). Re-brief the lane.
- A set whose mockups all share today's structure is flagged at the top of the owner's list, with
  an offer of one more round of blind lanes (skill `design-review`, Mockup set check).
- The designer lane writes only in the design folder (guard rule `designer-scope`).
- After the cull, the builder and the design reviewer run as usual (decision design-agents).
