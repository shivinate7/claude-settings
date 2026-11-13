---
name: design-explore
description: Use before the builder on a lane that explores a screen, a new screen or a redesign. Spawns designers in blind, informed and directed kinds, so the owner can cull a varied set of mockups. Not for a small change to an existing screen.
---

Run this in the orchestrator. Agents never spawn, so the orchestrator spawns every designer.
The ruling is decision design-agents, 2026-10-27. The owner wants a mix of control and new ideas
between the mockups.

In this skill, "the repo" is the session's repo, and `<repo root>` is its root.

## Designer kinds

Each designer is one agent: agentType `designer`, Opus (`agent-model-cap`), in its own
worktree (`parallelism-each-own-checkout`).

- **Blind designer.** Build the brief from the template `blind-brief.md` beside this file, and from
  nothing else. It holds the user's job in their own words and the things the job handles. It
  also holds the device and its poses, and fixed House rules and Deliver text. It never names the current
  screen, a view of today's product or its code. It never names a screenshot, a mockup, a path or
  link, the spec, the tokens, or a keep or match rule. It holds no colour, font or spacing value of
  the repo, so it has no Palette section. The orchestrator reads the job and the data from the spec or the
  owner's words, and writes them in plain words. A blind designer shows ideas the repo's habits would
  hide. Each designer's worktree holds the code, spec, tokens and mockups, and the guard
  `designer-scope` limits writes only, so the brief and the designer's own instruction keep it blind.
  Colour, type and spacing come from the house `tokens.md` only. The orchestrator checks a finished
  blind mockup for a repo hex before it shows it to the owner.
- **Informed designer.** The brief gives the current screen, its mockups, the spec and the tokens. Its
  second line is `Blind designers: <n>`, the count of the run's blind designers.
- **Directed designer.** An informed designer plus one named direction, such as denser, phone first, or one
  primary action. The orchestrator picks directions that differ from each other.

## Default mix

Per screen: two blind designers, one informed designer, two directed designers. The mix is a default. A brief or
the owner may change it, but a run keeps at least one blind designer unless the owner asks for none. Then
each informed and directed brief carries `Blind designers: none, owner: "<the owner's words>"`. A small change to an existing screen skips this skill and gets one informed
designer. A text-only change gets none (decision `design-agents`).

## Procedure

1. **Write the briefs.** Use the designer kinds above. The first line of each brief is
   `Designer kind: blind|informed|directed`. A directed brief adds its direction. The skill always names
   the kind; a designer reads a brief with no kind as informed. The brief gives the designer its `<n>`.
   A blind designer never reads other files in the design folder, sibling designer mockups included. Point the brief at files; never paste them
   (`tokens-point-brief-at-files`). Write each brief to `<scratchpad>/design-explore/<screen>/<screen>-<kind>-<n>.md`.
   The Device section comes from `python3 ~/.claude/lint/layout.py devices <repo root>`: the repo's devices in
   order, first device first. Do not type a device list of your own. Outside an iOS repo, a mockup draws the first device only. On request, or if the layout breaks between them, it draws the rest too.
   In an iOS repo (skill `ios-apps`, section Mockups), each brief names skill `ios-apps`, and the Device
   section names both Duo poses, folded first. Each mockup draws both poses.
2. **Check the briefs.** Run `python3 ~/.claude/hooks/blind_brief.py --run <that folder> --root <repo root>`. Add one
   `--current <view>` per view name of today's product that is not a plain word of the job. If the
   owner asked for no blind designer, add `--owner-asked-none "<words>"`. Exit 0 is clean. On exit 1,
   rewrite each brief it names and run it again. The same check runs at each designer spawn
   (hook `blind_brief.py`), but only this run sees the whole set and the view names.
3. **Name the files.** Each designer writes `<screen>-<kind>-<n>.html` and
   `<screen>-<kind>-<n>-notes.md` in the design folder. `<kind>` is `blind`, `informed` or
   `directed`. `<n>` counts the designers of that kind, from 1. The orchestrator assigns it in the brief. So designers never collide. Each mockup
   prints its designer kind on the page. A directed mockup also prints its direction.
4. **Spawn all designers together.** The designers share no input, so they run in parallel. Designers never talk
   to each other (`parallelism-no-mid-task-talk`).
5. **Collect.** Read each report, never a transcript. Grep each blind mockup for the repo's own colour
   (`python3 ~/.claude/lint/repo_colour.py <repo root>`). Grep it also for each colour in the repo's token
   files, as hex, rgb() and hsl(). One hit means that the designer leaked, so redo it. In an iOS repo, run
   `python3 ~/.claude/lint/check_ios_mockup.py <mockup>` on each mockup of each designer kind; on exit 1, redo
   the designer. Then run the structure check of skill
   `design-review` (Mockup set check) on the whole set. Give the owner one list: each mockup with its
   path, kind and direction, and the structure verdict of each.
6. **Gather.** Each designer pushes to the branch its brief names, so each brief names one branch per designer. The orchestrator copies every designer's pair onto the
   step's design branch, so the owner sees the whole set in one place.
7. **The owner culls** from the whole set. The orchestrator renames the kept pair to `<screen>.html`
   and `<screen>-notes.md`, and deletes the rest in the same branch. Git keeps them. It names the
   kept path in the briefs of the builder and the design reviewer, and the builder builds to it
   (`agents/builder.md`). Then the orchestrator opens one PR of only the kept pair, into the repo's design folder (the `design`
   kind in `~/.claude/lint/layout.json`). The PR goes through the repo's normal PR path and merges
   there, per decision `waiting-data-in-repo` (fb-1458-1): a repo's artifacts live in its git. The
   builder builds to the kept path on the design branch and does not wait for that PR.
8. **Clean up.** Push each designer branch to `archive/<branch>`, then delete it locally
   (`shared-trees-archive-then-delete`).

## Rules

- A blind brief that leaves the template, or names the current screen, its code, a mockup, the spec,
  the tokens or a keep or match rule, or holds a colour, font or spacing value, is a defect. The hook `blind_brief.py` refuses the spawn
  (decision blind-briefs-use-a-template). Re-brief the designer.
- A set whose mockups all share today's structure is flagged at the top of the owner's list, with
  an offer of one more round of blind designers (skill `design-review`, Mockup set check).
- The designer writes only in the repo's design folder (guard rule `designer-scope`).
- After the cull, the builder and the design reviewer run as usual (decision design-agents).
