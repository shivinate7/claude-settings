# A check reads triage's outbox against main

## The ruling

When triage reports status, a check lists each owner ruling in the outbox. For each ruling it says
whether the ruling's home on main holds its words.

- The outbox is `roadmap/outbox/<session-slug>.md` on the record branch, one file per session (skill
  `project-ops`). It is not the feedback log (term `feedback log` in GLOSSARY.md).
- Rulings not yet on main are kept in one store, not in the outbox: decision `ruled-store-one-home`
  (its ruling paragraph). The check reads the outbox for now, as R6 says.

Owner, 2026-11-10 15:22 CST, restart plan R6: "yes but it's tbd if an outbox is the right spot right?
but for rn it only make senses that it is read".

## Not built

The check is not built. No script reads the outbox against main. The operating model has triage read
the outbox at each wake (skill `project-ops`, its operating-model template). Step
`outbox-ruling-home-check` is the build.

Cost, planned: once per triage status report. It reads the outbox and main's files. It writes no file
and starts no long-lived process.

Kind: build
Plan: docs/plans/restart-plan.md#stage-4-make-the-roadmap-and-triage-mechanical (all)
