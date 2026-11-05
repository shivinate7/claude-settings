# Handoff: step craft-book (shivpedia plan)

## Goal

A practice learned once is used again in each later repo and session (owner, 2026-11-01 21:02 CST,
roadmap step `craft-book`, the experience book).

## Owner rulings

- 21:05 CST: the book is named shivpedia. It lives in claude-settings. The step slug stays `craft-book`.
- 21:06 CST: tight and low slop. Rewrite in place, never append. GLOSSARY.md moves into shivpedia.
- 21:07 CST: experiences, not commandments. Widen to a prose refactor plan. Build nothing until the
  owner signs off on the whole plan.
- 21:08 CST: shivpedia stays current through the same shared mechanism as the map and triage.
- 23:31 CST: each owner question leaves the session through send_message to the coordinator, in the
  same turn.
- 2026-11-02 12:31 CST: wind down.

The 21:06 and 21:08 rulings have their home in the plan's header. They land as decision `prose-forms`
in build lane 1.

## State

- Branch `prose-homes-shivpedia`. Plan head f3c93049. Draft PR #1034, "Plan: one home per kind of
  prose, and shivpedia", is open and not merged. It changes one file:
  `docs/plans/prose-homes-shivpedia.md`.
- Review: 3 rounds, each with two blind reviewers (round 1 haiku, rounds 2 and 3 sonnet). Every round
  ended FAIL. All findings are fixed in the plan. The fixes for round 3 came after its review. The cap
  of three rounds allows no fourth round.
- Built: nothing. The plan is the whole output.
- Nothing is left unpushed. No agent or server is running.

## Open questions (owner; sent to the coordinator 2026-11-01 23:39 CST)

- Q0: sign off on the whole plan, so that build lanes start in the order of the plan's section 8.
- Q1: the code name for one item. Recommended: `experience`.
- Q2: how a lesson from another repo comes in. Recommended: through each repo's outbox, read by
  triage.
- Q3: which reports carry `Lessons:`. Recommended: builder-shaped reports.
- Q4: a registry of generated pages. Recommended: not now.

## Next step

After sign-off:
1. Send lane `test-practices-first-principles` (draft PR #1028, decision `test-practices`) one
   message with the path `skills/shivpedia/testing/` and the list of practices to move.
2. Brief the build lanes from plan section 8, starting with `glossary-to-shivpedia`.
