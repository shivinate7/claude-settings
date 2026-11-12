# Owner rulings relayed to triage, Nov 12

Each line: the ruling, who relayed it, and its home on main. A lane lands each in its home; this file holds
them until then.

## R42 part 2, the merge flow after Anthropic's (step merge-flow-after-anthropic)

Relayed by the retrospective (session_013NEJKz5AWFJhGvmCUoi6wQ) from the owner's chat.

- Q1, 09:42 CST: option a. All repos, the child repos too, switch to per-lane merge together; each child repo
  first gets its own stable branch and revert route; the R42 lane session carries every repo. Owner's words:
  "none of the child repos are running rihgt now -- so if that makes A easier to do right now that's fine with
  me". Home: decision uniform-over-variants, with step merge-flow-after-anthropic pointing to it.
- Q2, 09:44 CST: a lane moves its PR from draft to ready by judgment: once, after its last review and lane lint
  pass, never per push; a PR that will not merge never goes ready. Owner's words: "it needed to be judgement
  based right so that way not every single pr auto starts CI". Home: decision draft-until-reviewed, rewritten
  in place when the switch lands. Answers page item 544.
- Q3, 09:46 CST, confirmed 09:48 CST ("q3 correct"): option i. A red main stops merges only until the revert
  merges; the revert's run is then read like any other. Home: decision no-merge-onto-red-main.
- Q4, 09:46 CST ("g is fine"): a revert is an ordinary lane PR merged with --base-red-ok; no `merge --revert`
  command. Home: skill ci-hygiene, its "Never revert" line.
- Design yes, 09:48 CST ("r42 -- yea that's correct yes?"): docs/plans/r42-part2-design.md (branch
  claude/ecstatic-euler-capib9) with the refuter's six changes and the Q1-Q4 picks. Answers page item 543.
  The lane merge-flow-after-anthropic started 09:49 CST (coordinator); the design lands on main with its first PR.

## Archiving (step handoff-lands-tracked-first)

Relayed by the retrospective.

- 09:42 CST, option a: whoever starts a session answers for archiving it. The batch runner archives PR lanes
  right after each merge for the coordinator; the coordinator archives every other finished session it started,
  at each wake, once its report is read.
- 09:47 CST: the lane also leaves its handoff where it can be found: it commits it to
  roadmap/outbox/<slug>-handoff.md before it tags itself archive-ready. Home: decision session-tiers, Archiving
  scope; skills/project-ops/templates/brief.md.

## Stale drafts

- 09:49 CST, in the coordinator's session, option a: "close the 436 PRs listed in plans/stale-drafts-2026-11-12.md,
  minus #1755 and #1725"; no close comments, no branch deletes. Record: plans/stale-drafts-2026-11-12.md.

## q_max Past Rates at 1440 px (page item 550)

- 10:27 CST, in the coordinator's chat: option a as a stopgap (Clear Filters and Price Date may fold under the Filters
  pill at 1440x900 on Past Rates; the EPI2B-3 check is re-pointed for Past Rates only), and a debt too: q_max
  decision D-649 as a whole is a stale screen-layout lock he does not want. Lane qmax-browser-main-red builds a and
  files the debt in q_max's debt store.

- 12:10 CST, relayed by the coordinator: "Custom connectors are not allowed -- so we can do route B". Page item 558 closed; decision waiting-page-one-store moves to route B (lane page-data-one-store); steps page-git-connector-probe and page-one-store-answers folded.
- 12:14 CST, in chat, relayed by the retrospective: "ah ok C is good go for it": page item 559 pick c, each failing required job wakes the batch runner as it fails, no cancel; R4's lint-first cancel stays. Step red-job-wakes-runner; plan R50.
- 12:08 to 12:11 CST, relayed by the coordinator: he cannot see coordinator picks to overrule them, "this needs to be mechanized", and "you also need to literally mechanize the verification that something was queued". Steps pick-reaches-page and msg-claims-vs-git; picks posted as stands items 560-583.
- 12:40 CST, in chat, relayed by the coordinator: page item 593 pick a: "the artifact is never operated upon by two accounts at the same time ... so as long as the artifact/data gets exported in a timely enough matter (not real time) it's morerso okay ... if ... the setup with all the lanes + triage is causing some sorta internal lag, then we should still be open to the switchr otue". The page database is the one store; git gets a timely export as backup. Home: decision waiting-page-one-store (lane page-data-one-store, #2829). Route B steps parked as the fallback; item 592 closed as moot.
- 12:33 and 12:35 CST, relayed by the coordinator and the retrospective: "it's weird that ure making half-baked calls", then "sure approved" on the retrospective's diagnosis. Plan R51, "A pick reads its ruling before it is sent", home plans/restart-plan.md on branch restart-plan (a2b2c8b52): a coordinator pick cites a ruling or "no ruling found: <search>" (step pick-ack-past-ruling); a pick that never reached the page is caught (step-pick-claims-match-page); lanes send hand-ins to the batch runner and questions to triage, so the coordinator gets only picks; a step slug that does not exist is caught (send-message-refs-resolve).
- 12:54 CST, page save: 602 a (cap-lift end time asks, any length); 586 a (cut run counts as a sample; step time-limits-end-hangs-only); 601 a (override ends on use, `override off` or next typed message; Opus ask until session end or `opus off`; step owner-override-one-route); 597 a (rule-bearing files keep the merge flag; decision claude-md-change-is-flagged rewritten); 579 b, "isn't all four parts overkill" (a new fact alone passes a ruling challenge; step ruling-challenge-passes). 595 none of these: "you're taking my ruling no hard fixed numbers too broadly and seriously..." R37 is read narrower: it aims at limits that cut work off; the 14-day missing-hook window stays.
- 13:07 CST, chat (relayed by the retrospective 13:08 CST): R52, batch runners on Sonnet 5.5 at medium effort; it becomes the default if no issues arise (home decision agent-model-cap; step model-table-one-home). R53, CI and merge alarms wake the batch runner and open no GitHub issue (steps main-job-cap-alarm, red-job-wakes-runner). Both in plans/restart-plan.md, branch restart-plan 4c91998.
- 13:12 CST, page save: 608 a, 609 a, 610 a (accepted picks). 606 none: "dont those hooks go to any and all repos that call claude-settings? have we reviewed what the claude-settings install actually does to a repo as i feel liike this is a mistype"; item reopened with the install facts.
- 13:20 CST, chat (relayed by the retrospective 13:21 CST): R54 pick a, "this is good, it can be an active nudger / checker against coordinator too right" (step coordinator-session-board rewritten; plan aa190fd). 13:19 and 13:21 CST: R55 pick d, "Express lane, and cancel a running batch for it too" (merge-flow lanes go to main first; plan 4fefc9f; home decision no-merge-during-batch-ci, which skill ci-hygiene step 8 points to (plan b152ca6); seven steps cite it).
