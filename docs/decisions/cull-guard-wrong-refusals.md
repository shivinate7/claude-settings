# Cull the guards with recorded wrong refusals

## The question

Which guards and checks with a recorded wrong refusal get fixed or deleted, and what does a wrong refusal become after that?

## Ruling

It sits beside decision `cull-rules` (how a cull runs, owner ruling 2026-10-17). It does not change that record.

Owner ruling, 2026-11-10 15:04 CST, relayed by the retrospective session. It is R5, the guard cull in the restart plan (record branch `restart-plan`, stage 3, step 6). The owner's words: "i'd say option e works for now with a revisit maybe to threshold lanes if it turns out to be problematic".

- One cull lane fixes or deletes each guard or check with a recorded wrong refusal, whichever costs less. The cost of deleting includes the harm the guard stops (rule `building-guard-needs-incident`).
- The source is each recorded wrong refusal in the notes file of the debt store, and the eight debt files that name false alarms: `bg-end-false-alarms`, `heredoc-written-run-false-alarm`, `pycache-rm-false-alarm`, `stamp-read-false-alarms`, `build-disk-guard`, `inplace-edit-under-0-9-flagged`, `scan-quote-led-password-host`, `unstarted-guard-held`. Counted 2026-11-10: 80 notes entries (53 that say "false alarm", 24 with "false-alarm" in the slug, 3 that say "false refusal"). Left out, because each names no refusal: `guard-log-one-machine`, `press-link-unnumbered`, `prove-judge-all-unknown-rate`, `pair-title-quotes-short-id`, `carried-run-reedit-overstated`.
- After the cull, a wrong refusal is a note only: one line in the notes file, with no red test and no decision edit, as the notes tier sets.
- The cull lane is not built.
- Not in force, a possible later rule: if wrong refusals become a problem again, revisit threshold lanes. A guard with 3 recorded wrong refusals gets its own lane.

## Why

A guard that goes red when nothing is wrong is spent, because its reader stops reading it (`guard-that-cries-wolf-is-spent`). The owner gave no reason for R5. This line gives the reason from that decision.

Kind: process
Home: rule:building-guard-needs-incident
