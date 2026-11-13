# Artifact lane: recovered sources

Copied 2026-11-03 17:40 CST from the transcript of the previous coordinator (session_013NEJL2pASwRjgJDnsvnpNe),
read with `list_events`. Its scratch files were not carried over. Each quote names its event uuid. Times are CST.

## Owner feedback

- fb-1456-1 (14:56 CST, event 99e95903-7fe1-4efb-9848-cfed57e54fe5), verbatim:

  <!-- ste-disable-next-line STE001: verbatim owner and coordinator words -->
  > "yeah in general i mean artifacts will be torn down and spun up independently as i switch accounts thats why i was telling u about all the artifact export rules i need and that actually goes for design work too. so many mockups/artifacts are made on one account and then not visible in another, there needs to be an easy way for them to be cross-refernecable and if that means commiting them on github so be it im fine with htat."

- fb-1458-1, fb-1458-2 (14:58 CST, event 760534fd-d5f4-4aca-8777-970a479f2647), verbatim, then "A":

  <!-- ste-disable-next-line STE001, STE008: verbatim owner and coordinator words -->
  > "i've found countless examples of design mockups made by the designer agent not going into my repos' design folders. so that's prboably another gap u need to go look into"

  The "A" picks option a of event e7ccdec6-0eed-4233-a037-c02582c324ef, verbatim:

  <!-- ste-disable-next-line STE001: verbatim owner and coordinator words -->
  > "Git is each artifact's home, and the claude.ai link is just one account's view of it. An artifact is published only from a file in a repo, and listed in that repo's registry. The export saves the page HTML, its supporting files and its database. A cite names the artifact's id and its repo path... That also settles 14 roadmap step links: under (a) they become `artifact:<id>` cites"
- fb-1509-1 (15:09 CST, event a1426829-348d-4fcf-be1d-27b6e68a2f22): degen PR #324 (merged as 5de5c55d) built its own
  export, `waiting_export.py` in its tools folder. Coordinator reply (event e67a56c5-94e4-4b8c-99bf-5f633d3fd37f): a second home for
  one capability; its secret scan raised 5 false alarms, so degen cut its scan to secrets only. A later review says
  this repo's scan refuses 4 of those 5 strings (event 31f89299-0895-4716-aa51-d39823b17299). The 5 strings were not
  recovered.
- fb-1512-1 (15:12 CST, event 300825af-c8df-44eb-a3ae-41d2d069eefa): "wb". It answers the coordinator's revised
  question (event f02abcb7-7474-4390-9b96-16384e4ee314, 15:12 CST), which recommended Wb and said: "the export should
  save the HTML only when it actually changed". Every repo's artifact copy lives on its
  record branch (`roadmap`), pushed by the page writer with no PR. Degen moves its copy there and retires its export to
  call this repo's.
- fb-1510-1: no owner message. The coordinator's standing note, quoted below.

## Designer-gap notes (fb-1510-1)

Explore (sonnet), 2026-11-02 15:10 CST, event 58a1960f-7cf0-4bd9-b82c-b6b7a886bd56. Verbatim:

> Counts, html in docs/design: on origin/main | only on a non-main ref. claude-settings 15|3; q_max 19|0; banchi 8|0;
> degen 14|0; mailaudit 6|0; joyous 0|0. banchi: 7 more in `designs/d4-*` on origin/roadmap. A never-pushed file shows
> nowhere.
>
> Queue page (claude-settings) designData: 33 mockups. 1 exact file match (only on a worktree-agent branch); 8 topic
> matches on main; 22 d4 on origin/roadmap; 2 home-repo unknown.
>
> Causes, ranked:
>
> 1. Nothing merges the kept mockup to main. agents/designer.md:82 stops at "push your own branch";
>    skills/design-explore/SKILL.md:67-74 gathers onto an unnamed design branch with no PR step. The designer writes
>    into the repo that spawned it (designer.md:14-15): banchi screens drawn from claude-settings never reach banchi.
>    Fix: one PR of the kept mockups into the target repo's docs/design; the brief names the target repo.
> 2. The waiting page is the only copy. skill `waiting-page`, "Add a design", step 3 pastes the HTML into the page, and its last paragraph drops it
>    when the question closes. Fix: "Add a design" must find the file on origin before writing the item.
> 3. An unmerged mockup branch was deleted: degen's `jd-deferred.html` in its design folder (owner pick B, 2026-10-26 23:45 CDT),
>    cited at degen's specs folder, `plan.md:1945`, and native/Degen/JdDeferredPage.swift:5; on no ref. Product repos hold 0
>    archive/* branches. Fix: refuse a branch delete whose diff holds docs/design files main lacks, unless archived.
> 4. Unpushed worktree loss (unmeasured): no hook pushes for the designer; a container reclaim loses it. Fix:
>    SubagentStop for the designer refuses to end unless HEAD is on origin.
>
> Ruled out: janitor sweep, .gitignore, designer-scope guard.
>
> No debt on main names this. docs/decisions/mockup-home.md exists only on origin/mockup-homes (unreviewed, judges
> path shape only).
>
> Owner-only: on the Mac, `git -C <degen> worktree list` and `git reflog` to find jd-deferred-mockup.

Line numbers in the quote are as of 2026-11-02 and may have moved.

## The 14 step links

Coordinator to owner, 14:56 CST (event 46a1a427-f298-4bbe-9bf1-f17686643fae): "14 roadmap step files hold bare links
today. A PR's CI doesn't fetch the roadmap branch." Option a: an agent fixes the 14 links, then the check refuses bare <!-- ste-disable-line STE008: verbatim owner and coordinator words -->
links at the write to the roadmap branch, in the guard that checks page writes.

Today's list (`python3 lint/check_artifact_cites.py --steps list`, 2026-11-03): c100, c103, c121, c127, c130, c52, c55,
c71, c81, c89, c90, c91, layout-page-url-live, o2.
