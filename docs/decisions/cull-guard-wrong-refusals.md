# Cull the guards with recorded wrong refusals

## The question

Which guards and checks with a recorded wrong refusal get fixed or deleted, and what does a wrong refusal become after that?

## Ruling

It sits beside decision `cull-rules` (how a cull runs, owner ruling 2026-10-17). It does not change that record.

Owner ruling, 2026-11-10 15:04 CST, relayed by the retrospective session. It is R5, the guard cull in the restart plan (record branch `restart-plan`, stage 3, step 6). The owner's words: "i'd say option e works for now with a revisit maybe to threshold lanes if it turns out to be problematic".

- Triage's reading, not the owner's words: the cull fixes each guard or check with a recorded wrong refusal. It deletes one only when its false alarms cost more than the harm it stops (rule `building-guard-needs-incident`). The restart plan words the choice as "whichever costs less". The owner is asked whether R5 replaces that gate (asked 15:21 CST).
- The source is the lines in the notes file of the debt store that say "false alarm", as ruled. Count method, run 2026-11-10: `grep -c -i 'false alarm' docs/debts/notes.md` gives 60 lines, and `grep -i 'false alarm' docs/debts/notes.md | sed -E 's/^- ([^:]+):.*/\1/' | sort -u | wc -l` gives 56 entries. Three of the 60 name no refusal (`guard-log-one-machine`, `press-link-unnumbered`, `prove-judge-all-unknown-rate`), and the lane drops them.
- Triage addition, not ruled, which the cull lane may weigh: the notes lines that say "false-alarm" in a slug without "false alarm" (`grep -i 'false-alarm' docs/debts/notes.md | grep -c -v -i 'false alarm'` gives 26 lines, and two name no refusal: `pair-title-quotes-short-id`, `carried-run-reedit-overstated`); the 3 lines that say "false refusal" (`grep -c -i 'false refusal' docs/debts/notes.md`); and eight debt files that name false alarms: `bg-end-false-alarms`, `heredoc-written-run-false-alarm`, `pycache-rm-false-alarm`, `stamp-read-false-alarms`, `build-disk-guard`, `inplace-edit-under-0-9-flagged`, `scan-quote-led-password-host`, `unstarted-guard-held`.
- After the cull, a wrong refusal is a note only: one line in the notes file, with no red test and no decision edit, as the notes tier sets.
- The cull lane is not built.
- Not in force, a possible later rule: if wrong refusals become a problem again, revisit threshold lanes. A guard with 3 recorded wrong refusals gets its own lane. The number 3 came from the retrospective session's relayed proposal, not the owner's words.

## Why

A guard that goes red when nothing is wrong is spent, because its reader stops reading it (`guard-that-cries-wolf-is-spent`). The owner gave no reason for R5. This line gives the reason from that decision.

Kind: process
Home: rule:building-guard-needs-incident
