# o8 option (c), lane o8-session-lines: outbox

State: paused, Oct 28. The orchestrator declined the reading in plan point 1. Triage puts it on the waiting page for shiv, recommending: drop (c), keep (a). Build nothing until the orchestrator messages the answer.
Why paused: the plan changes who writes the page's database (brief: plan first).

## Plan (sent)
1. c136 conflict: c136 says sessions "never write the page themselves". (c) has each session write
   `live/<session id>`. Reconcile: one writer owns `items` and `rank`; a session owns only its own
   unranked `live` doc, the same pattern as `receipts/<id>` on main (skills/waiting-page, "The database").
   A live line is not a question, so nothing needs ranking. If the orchestrator reads c136 as
   "no session writes the database at all", (c) becomes "sessions send state to the writer", which is (a) again.
2. Target page: the `waiting-page` key in .claude/layout-extras.json (c136 makes it the one page).
   Until c136 merges, the roadmap viewer renders `live` from its own database only.
3. Cost measure: one ArtifactData call per state change; no process, no file, no hook, no timer.
   Mac write measured by c71 (Oct 26). Windows unmeasured: a cloud lane cannot run it; needs a local
   liaison. Windows sessions read "unknown" until then.
4. Found: meta/page on the pilot page has no `writer` field (read Oct 28).
5. Build if approved: skills/roadmap SKILL.md paragraph + viewer merge of `live` with --live by title
   (newer wins, >6h quiet, malformed skipped); waiting-page protocol line; fixture test red first.

Deferred: why: c136 (Oct 27, after the Oct 26 (c) ruling) says sessions never write the page; shiv decides whether (c) survives. Windows measure (point 3) stays open if (c) survives.
