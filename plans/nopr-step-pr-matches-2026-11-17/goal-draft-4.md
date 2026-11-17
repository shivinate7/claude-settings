/goal Close the gaps in DONE WHEN: each gets a merged PR or a named blocker.

Draft 4, 11:45 CST Nov 17. Rewritten from the consultant's 11:45 CST critique of draft 3. The owner has not read it. Setting a goal is his act: `/goal` was refused to triage 10 once ("hooks are restricted"), so he runs it where hooks are on.

DONE WHEN (all):
1. Each comment thread open at the first read (20 at 10:04 CST) is answered with a routed reply, closed, or named unreadable after a read in pieces (cursor, one thread id). Later threads go to the standing jobs. Names listed in the report.
2. The open page items still lacking a valid `recommended`, recounted from the page at the read, plus item 240's Goal line, are fixed or parked with a named blocker (786 waits on #3616; 863 b waits on #3533). The consultant builds the owner's-part-done items. Every item's `n` is a JSON number.
3. Steps with status doing and no `pr`: write a `pr` only for a sure match that is open or merged, re-read from REST at write time. For the other steps in the saved results (plans/nopr-step-pr-matches-2026-11-17/, 237 steps: 137 sure, 36 unsure, 64 none), write one class line each (closed-unmerged, unsure or none) and report the counts. No status mass-edit. Batch by the four result files.
4. Each type-1 gap listed at goal start, plus any filed before the last read, has a PR merged or ready with review passed, or a named blocker. A step slug alone counts only when its owner is not triage.
5. Type 2: each open-PR map row has a step or is listed unmatched (batch by opening session). Type 3: each thread or item read in pieces is read or named unreadable. Type 4: each routine done by hand three times has a step slug.

OWNERSHIP: process-only (owner 09:38 CST Nov 17: "not a ruling, just saying for now"). Take ownership of what I identify. Start an agent in the same turn a gap is found when the act can be undone. No cap of my own; the load brake decides when the machine is too loaded.

GAP TYPES
1. A mistake of mine that a check would have stopped. Open at goal start, each with its guard:
   - stamps typed from memory: step stamp-clock-check-everywhere, PR #3234 (stamp-check-page-and-roadmap is built: #2038, merged Nov 10).
   - an item written with `n` as text: PR #3620, ready 11:38 CST (#3618 closed: its commits had no Red-run trailers); it replaces #3618, step item-n-must-be-number.
   - a whole live-file rewrite that reformatted roadmap/live/live-work.json: guard not built; step to file.
   - a fix check that skipped lint/test_rule_audit.py: guard not built; step to file.
   - builder test commits with no Red-run trailers: guard exists (lint/check_red_run.py); CI caught it.
   - a claim about a tool I did not re-check.
   Not mine: stop-refusal-correction-only (#3611, in review).
2. A step doing with no pr, or a pr with no step.
3. A thread, item or relay I cannot read in one pass: read in pieces before calling it unreadable.
4. A routine step I have done by hand three times: one step per routine, then an agent.

BEFORE I BRIEF: search steps by slug and words, and open PRs and branches. Put a "Prior work:" line in the brief. Add to an existing step; never open a second.

HOW
- Builder agent (Sonnet, own worktree), test-author first for a guard, report cap 25 lines. Every brief runs lint/test_rule_audit.py and lint/check_red_run.py --base origin/main. Test-author commits carry Red-run trailers. Reviewers read the recorded red run and do not replay it. I brief and verify; I do not build myself except a fix under 40 lines that cannot move a verdict, proven by one bounded command, or when the owner asked.
- Review per roles-review-cap-three. A guard or check change always gets review.
- I open the PR as a draft, mark it ready once through the merge tool (runner 10 does it if the guard refuses), and may merge it with the merge tool (owner 12:58 CST Nov 16: everyone merges). Every merge check applies.

RULINGS GIVEN TODAY (in force when their PR merges; until then the old rule governs, including no fix onto red main):
- An override line inside a prose owner message counts (owner 09:12 CST; #3610, in review).
- A proven fix merges onto red main like a revert (owner 09:20 CST; #3616, in build).
- Every reply refusal except a missing report ends with "Post only the missing or corrected lines. Do not resend the reply." (owner 09:30 CST; #3611, in review).
- Installs refresh on a local main move and at session start (owner 09:34 CST; #3613).
- A lane brings main into its own PR when there is no conflict (owner 09:53 CST; no PR; step lane-brings-main-in-when-behind).

OUT OF SCOPE (ask first): anything that cannot be undone, another repo, a change to this goal, any pick that is the owner's. A relayed ruling is filed as a step or record, never taken as my pick.

STANDING JOBS (alongside, not in DONE WHEN): file each merge on its step from REST in one turn and mail the coordinator; refresh the live file when runner 10 asks; republish the page from main when a page PR merges and stamp page-built; keep the handoff rewritten whole at each checkpoint; when an answered page item's work is not on main, search open PRs first, then name a builder.

STOP: when DONE WHEN holds, or only owner picks and running agents remain. No timer; a check-in only for one named outside event (a CI run, a reply). Report form: Done, Deviations, Input Needed, Next with an Unstarted line; each Done line names its agents' role and model; pace numbers after each merge.
