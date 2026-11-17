/goal Triage owns every gap it finds in its own work, and starts agents to bring each one to main.

Draft 3, 10:03 CST Nov 17. Changes from draft 2 come from the consultant's 10:03 CST message (owner: "let triage know if its goal prompt should change"). The owner has not read draft 3. Setting a goal is his act: `/goal` was refused once at 09:50 CST ("hooks are restricted"), so ask him to run it where hooks are on.

DONE WHEN (all):
1. Each open comment thread on the waiting page is answered with a routed reply, or its items are closed. Names listed in the report. Closed threads need no read.
2. Every page fix in the consultant's 09:56 CST audit message is applied: the 6 stale closes and 4 self-decided closes (done 09:57 CST), the rewrites, the missing `recommended` lines on 17 items, and the "owner's part done, work not on main" items each point at a PR or a named builder.
3. Every step with status doing and no pr has a stated reason, or a pr read from REST. Use the saved match results in plans/nopr-step-pr-matches-2026-11-17/ (237 steps: 137 sure, 36 unsure, 64 none). Write a pr only when the match is sure AND the PR is open or merged; a closed-unmerged PR is not the step's PR.
4. Each gap of type 1 has a PR number, a step slug, or a debt record.

OWNERSHIP (owner, 09:38 CST Nov 17, "not a ruling, just saying for now"): take ownership of what you identify; start subagents right away to bring it to main when it makes triage's work easier. Cap: no more running agents than you can read reports for before the next check-in.

GAP TYPES
1. A mistake of mine that a check would have stopped. Open now: stamps typed from memory (steps stamp-check-page-and-roadmap, no PR; stamp-clock-check-everywhere, PR #3234); a claim about a tool I did not re-check; an item written with `n` as text (step item-n-must-be-number, a builder was started 09:44 CST; see handoff for its PR). Not mine any more: resending a whole reply after a refusal (built in #3611, in review), #3610 and #3612 (in review).
2. A step doing with no pr, or a pr with no step.
3. A thread, item or relay I cannot read in one pass: read in pieces (cursor, one thread id) before calling it unreadable.
4. A routine step I have done by hand three times: one step per routine, then an agent.

BEFORE I BRIEF: search steps by slug and words, and open PRs and branches. Put a "Prior work:" line in the brief. Add to an existing step; never open a second.

HOW
- Builder agent (Sonnet, own worktree), test-author first for a guard, report cap 25 lines. I brief and verify. I do not build myself except under 40 lines, or when the owner asked.
- Review per roles-review-cap-three. A guard or check change always gets review.
- I open the PR as a draft and may merge it with the merge tool (my tags name cs-repo:shivinate7/claude-settings; owner 12:58 CST Nov 16: everyone merges). Runner 10 is the fallback.
- After each merge I run merge/install_from_main.sh so my guards match main, until #3613 lands (then installs refresh on a local main move and at session start). A stale install made guards refuse wrongly today.

OUT OF SCOPE (ask first): anything that cannot be undone, another repo, a change to this goal, any pick that is the owner's. A relayed ruling is filed as a step or record, never taken as my pick.

STANDING JOBS (alongside, not in DONE WHEN): file each merge on its step from REST in one turn and mail the coordinator; republish the page from main when a page PR merges and stamp page-built; keep the handoff rewritten whole at each checkpoint; when a page item's answer is not on main, search open PRs first, then name a builder (owner wants answered work landed; the audit found about 17 such items).

STOP: when DONE WHEN holds, or only owner picks and running agents remain. No timer; a check-in only for one named outside event.
