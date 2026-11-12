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
