# Cull the guards with recorded wrong refusals

## The question

Which guards and checks with a recorded wrong refusal get fixed or deleted, and what does a wrong refusal become after that?

## Ruling

It sits beside decision `cull-rules` (how a cull runs, owner ruling 2026-10-17). It does not change that record.

Owner ruling, 2026-11-10 15:04 CST, relayed by the retrospective session. It is R5, the guard cull in the restart plan (record branch `restart-plan`, stage 3, step 6). The owner's words: "i'd say option e works for now with a revisit maybe to threshold lanes if it turns out to be problematic".

- Owner answer, 2026-11-10 15:23 CST, relayed by the retrospective session, on the delete gate: "b (my pick, and triage's): t this is fine". The delete gate of rule `building-guard-needs-incident` stays. The cull fixes each guard or check with a recorded wrong refusal. It deletes one only when its wrong refusals cost more than the harm it stops. The restart plan words the choice as "whichever costs less".
- Owner addition, 2026-11-10 15:18 CST, relayed by the retrospective session, as ruled: "A is fine -- but the coordinator probably has way more data on how hooks have been acting than your small sample size does". The ruled sources are three. First, the "false alarm" lines in the notes file of the debt store. Second, the coordinator's record of hook fires. Third, three named fires: the lane pick guard's wrong fires, the Departs-from separator guard, and the Recovered-line guard. Count method for the notes lines, run 2026-11-10: `grep -c -i 'false alarm' docs/debts/notes.md` gives 60 lines, and `grep -i 'false alarm' docs/debts/notes.md | sed -E 's/^- ([^:]+):.*/\1/' | sort -u | wc -l` gives 56 entries. Three of the 60 name no refusal (`guard-log-one-machine`, `press-link-unnumbered`, `prove-judge-all-unknown-rate`), and the lane drops them.
- Triage addition, not ruled, which the cull lane may weigh: the notes lines that say "false-alarm" in a slug without "false alarm" (`grep -i 'false-alarm' docs/debts/notes.md | grep -c -v -i 'false alarm'` gives 26 lines, and two name no refusal: `pair-title-quotes-short-id`, `carried-run-reedit-overstated`); the 3 lines that say "false refusal" (`grep -c -i 'false refusal' docs/debts/notes.md`); and eight debt files that name false alarms: `bg-end-false-alarms`, `heredoc-written-run-false-alarm`, `pycache-rm-false-alarm`, `stamp-read-false-alarms`, `build-disk-guard`, `inplace-edit-under-0-9-flagged`, `scan-quote-led-password-host`, `unstarted-guard-held`.
- After the cull, a session that judges a refusal wrong records it as a claim line with `bin/guard-outcome` (see What counts now). A claim line holds the verdict; a note under docs/notes/ is written when a finding needs words a claim line cannot hold.
- Not in force, a possible later rule: if wrong refusals become a problem again, revisit threshold lanes. A guard with 3 recorded wrong refusals gets its own lane. The number 3 came from the retrospective session's relayed proposal, not the owner's words.
- Owner lean, 2026-11-23 23:02 CST, in the consultant's chat, on the question "false-alarm count per guard" (a: each false-alarm note names its guard; b: an outcome line in the guard log per judged refusal): "on question B, B seems a bit better than A -- would you disargee and say A?" The consultant agreed and took b as its pick on that lean, marking each line as a claim. The pick is the consultant's, not an owner ruling. It stands until the owner reverses it by saying so.

## What counts now

A guard's wrong refusals are its `false-alarm` claim lines in guard.log. The session that was refused writes a claim with `guard-outcome RULE false-alarm|right [--why TEXT]` when it judges the refusal wrong or right. `hooks/guard_core.py` `log_line` and `append_log_line` give the line format, and `record` calls both. The why text is capped at 200 characters.

A claim is unchecked. It stays the session's word until a person or a reviewer checks it before a cull.

Reader: `lint/guard_log_report.py --outcomes [--between START END]`, read at each cull. It prints per rule the refusals, the claimed false alarms, the claimed right and the false-alarm share, under a line that says the claims are unchecked. An outcome line counts in no refusal column.

Cost: one append per call, proved by `test_one_call_appends_one_line_and_starts_no_other_process` in `lint/test_guard_outcome.py`. No hook, timer or process.

Not counted: a refusal no session judged. The log holds no automatic outcome.

## Why

A guard that goes red when nothing is wrong is spent, because its reader stops reading it (`guard-that-cries-wolf-is-spent`). The owner gave no reason for R5. This line gives the reason from that decision.

Kind: process
Home: rule:building-guard-needs-incident
