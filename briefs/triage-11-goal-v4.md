# Triage 11 goal, version 4 (final, rewritten from the consultant's feedback)

Replaces goal v3. The owner pastes it with `/goal`; triage cannot set it.

## What v3 got right, and what it got wrong

Worked:
- Each gap named a proof, and each closed on that proof.
- The "WAITING names who, the act and the one event" rule kept real owner waits visible.
- "Owner questions go on the page only" kept questions in one place.

Did not work:
- Gap 2 asked for a CLAUDE.md grant for a step that was dropped. The check could never pass.
- It named a PR as the ledger's blocker. The real blocker was an owner item.
- The goal check reads only the transcript. Evidence from earlier turns was invisible after each compaction, and a legitimate wait read "not met" about 59 times. Each answer cost a turn and landed nothing.
- No line on throughput, on checking past rulings before asking, or on reading PR state from REST before writing "waits on".

Consultant's feedback on this text (11:12 CST Nov 18), applied: no fixed row states (the goal rots in an hour); list order is not work order; DONE WHEN says in words what a check reads as met; a report with no named reader is not written; no owner call lives in the goal (picks stay on the page).

## Goal text

GOAL (triage 11, claude-settings, v4): keep the owner's page and the roadmap true, and finish each thing the owner asked, so every row below ends merged, ready for a runner, or WAITING. Read each row's state live at every wake, from REST or the page, never from memory or from this text.

Scope: I write the page items and the roadmap record, file merges others make, and merge only my own docs PRs (40 lines, 3 files, role `standing`). Code goes to runner 10 as a branch head after lane lint passes. Out of scope: an act that cannot be undone, another repo's merges, a change to this goal, the owner's picks.

Rows (named by step or item; the list order is not the work order):
1. Outbox drain (step triage-outbox-drain): the J, R and U parts and the K notes (one note each in docs/notes by a PR, after the notes lints; step record-writer-knows-notes-rules).
2. Ledger of lost PRs (item ledger-unknown-rows): the rerun and publish to roadmap/backlog/lost-prs.json.
3. Blog practices to instill, each ending as a landed rule or check, not only a filed step: (a) measure what each review layer catches before changing a layer (items review-layer-catch-source and reviewer-eval-cases); (b) a verify skill per repo that drives the real thing (step verify-skill-per-repo); (c) a guard or check file a PR changes is judged by main's copy (item lane-lint-main-copy); (d) PR template lines Testing, Risk, How to revert, and risk tiers by change (the tier items); (e) guard stages off, observe, enforce (item guard-stages-observe); (f) count findings repeated across review rounds (measured; no guard built, because records hold verdicts, not findings). A finding is landed when its rule or check is merged on main (REST) or it waits on a named owner pick.
4. Lost work (step fix-check-other-records): the coordinator builds it; I file the merge from REST.
5. Guard steps from my own mistakes (each starts with a prior-work search): placeholder time in a message, check past rulings before posting an owner question, read PR state from REST before writing "waits on <PR>". The coordinator gives each a lane or agents.
6. Status-tab build (the coordinator's draft PR): when it merges, publish the ledger key and do act (c). The live page needs a republish after the merged page change; a one-item survival test of stored items comes first.
7. Each merge the coordinator relays gets filed (step by pr field, else by branch), and the consultant's change that lets any standing session merge a straggling PR.

DONE WHEN a check that finds only DONE or WAITING rows reads met. DONE is merged (REST) or ready for a runner. WAITING names the mover, the act and the one wake event, all read live; a row I could move myself is not WAITING.

Order of work: parallel, not in sequence.
- List order is not work order: start every row that is not WAITING at once, each with its own agents in its own worktree (one role per agent; read-only Explore agents for searches), in one turn.
- When a row blocks, start the next unblocked row in the same turn.
- Argue "at max parallelism" only by naming the rows that are open and why each cannot start.

Reporting:
- The page is the table. A report with no named reader is not written.
- When nothing changed, write one line and end the turn. Never repeat earlier proofs.
- A report that lands a commit, push or merge ends with Done, Deviations, Input Needed, Next. Done items say BUILT, RECORDED or OTHER, with a PR or commit on BUILT and RECORDED.
- Owner questions go on the page only, after reading the decision record for a past ruling.
- Times come from `~/.claude/bin/now-central`. Every id carries a plain gloss on first use.
