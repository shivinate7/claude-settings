# Triage 11 goal, version 4 (final, 10:36 CST Nov 18)

Replaces goal v3. The owner pastes it with `/goal`; triage cannot set it.

## What v3 got right, and what it got wrong

Worked:
- Each gap named a proof. Gaps 1 (PR 3639), 4 (PR 3642) and 6 (commit aa29166d62) closed on that proof.
- The "WAITING names who, the act and the one event" rule kept real owner waits visible (items 952, 953, 956 to 960, 962).
- "Owner questions go on the page only" kept questions in one place.

Did not work:
- Gap 2 asked for a CLAUDE.md grant for a step that was dropped. The check could never pass.
- Step 7 named PR 3627 as the ledger's blocker. The real blocker is owner item 962.
- The goal check reads only the transcript. Evidence given in earlier turns was invisible after each compaction, so it read "not met" about 59 times and I answered each time. That cost turns and landed nothing.
- No line on throughput, on checking past rulings before asking, or on reading PR state from REST before writing "waits on".

## Goal text

GOAL (triage 11, claude-settings, v4): keep the owner's page and the roadmap true, and finish each thing the owner asked, so every row below ends merged, ready for a runner, or WAITING.

Scope: I write the page items and the roadmap record, file merges others make, and merge only my own docs PRs (40 lines, 3 files, role `standing`). Code goes to runner 10 as a branch head after lane lint passes. Out of scope: an act that cannot be undone, another repo's merges, a change to this goal, the owner's picks.

Rows (the state is read from REST or the page, never from memory):
1. Outbox drain: PR 3647 (342 J notes) merged by runner 10. Then drop the J lines from roadmap/outbox/triage.md and file the merge on step triage-outbox-drain. Then outbox R (25), U (51) and K lines.
2. Ledger of lost PRs: owner item 962 answered, then the rerun and publish to roadmap/backlog/lost-prs.json.
3. Blog practices to instill (from the verification and code-review blogs; each ends as a landed rule or check, not only a filed step): (a) measure what each review layer catches before changing a layer (item 953); (b) a verify skill per repo that drives the real thing (step verify-skill-per-repo, ready for runner 10); (c) a guard or check file a PR changes is judged by main's copy (item 952); (d) PR template lines Testing, Risk, How to revert, and risk tiers by change (items 956 to 959); (e) guard stages off, observe, enforce (item guard-stages-observe); (f) count findings repeated across review rounds (measured; no guard built, because records hold verdicts, not findings). A finding is landed when its rule or check is merged on main (REST) or it waits on a named owner pick.
4. Lost work: step fix-check-other-records is in build by the coordinator (rebuild on main; stalled draft PR 2940 is closed as replaced when the rebuilt PR opens). I file the merge from REST.
5. Guard steps from my own mistakes (each starts with a prior-work search): placeholder time in a message (the future-stamp half is covered by rule message-time-matches-clock and draft PR 3234), check past rulings before posting an owner question, read PR state from REST before writing "waits on <PR>". The coordinator gives each a lane or agents.
6. Status-tab build (draft PR 3649, the coordinator's): when it merges, publish the ledger key and do act (c). After PR 3264 (merged 10:20 CST Nov 18) the live page needs a republish; a one-item survival test of stored items comes first.
7. Each merge the coordinator relays gets filed (step by pr field, else by branch). The consultant's change that lets any standing session merge a straggling PR (owner, 10:27 CST Nov 18) is filed when it merges.

DONE WHEN each row is merged (REST), ready for a runner, or WAITING. WAITING names who moves it, the act, and the one event that wakes me; a row I could move myself is not WAITING.

Reporting:
- Post one state table when a row changes. Put the PR number, REST state and CST time in it.
- When nothing changed, write one line and end the turn. Never repeat earlier proofs.
- Owner questions go on the page only, after reading the decision record for a past ruling.
- Times come from `~/.claude/bin/now-central`. Every id carries a plain gloss on first use.
- A report that lands a commit, push or merge ends with Done, Deviations, Input Needed, Next. Done items say BUILT, RECORDED or OTHER, with a PR or commit on BUILT and RECORDED.
