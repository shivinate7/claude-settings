# A mistake Claude made means a guard is missing

## Ruling

Owner, 2026-11-06 11:38 CST: AI sometimes assumes it broke something by accident. The way we work should make accidents hard, so a mistake is a strong sign, not a certainty, that a guard belongs there. Owning up to the mistake does not close the problem.

- The report names the guard that would have stopped the mistake: built (a PR or commit), queued as `step:<slug>`, or a debt.
- An apology alone is not a fix.

Owner, 2026-11-08 11:27 CST, typed in lane notes-fix-reverify-large: "any sort of thing that requires sessions to make habits should be triggers for a step to be created and a fix to be in the works or at least queued for one; this goes against our mandates of codifying stuff that can be mechanized rather than having temporal states".

- A habit, a brief line or a promise to remember is no guard. Only a PR, a commit, `step:<slug>` or a debt counts.

Incident, 2026-11-08 11:26 CST: a lane report said "Guard: future merge briefs run `lint/check_silent_undo.py` before the push." Its admission named the builders, not "I", so the check never read the guard line. The step for that mistake is `step:merge-main-silent-undo-precheck` (a push of a main merge is checked for dropped lines).

Incident, 2026-11-06: the coordinator ran `sed -i '$d'` on its feedback inbox to drop the last item. The command deleted the closing code fence instead. Only the Stop check in `hooks/feedback_guard.py` caught it, one turn later. The same day, the coordinator trusted a stale decision line and called a lane idle while the lane's PR was open.

More incidents, 2026-11-06, from the batch of PR #1034 (a batch of lanes), each with the guard it lacked. Neither guard is built.

- A suggested fix, a `.gitkeep` exclude, was pushed without a run of the repo's own code check, which then refused it. Missing guard: run the repo's own checks on a suggested fix before the push.
- A lane's new CI job was proven only locally, where its tools resolve. In CI the job could not load a dependency. Missing guard: a new CI job gets one CI run of its own before it joins a batch.

## The check

`lint/report_guard.py` refuses a report on a landed turn whose Deviations item admits a mistake you made and names no guard for it.

- An admission is a clause with a first-person word (`I`, `my`) before a fault word. Clauses split at punctuation and at because, since, but, while and although. "The test was wrong so I re-pointed it" passes.
- The fault words: wrong, wrongly, mistake, mistaken, by accident, accidental, accidentally, broke, clobbered, overwrote, misread, forgot, "trusted a stale", "trusted an old", "trusted an outdated" and "instead of checking". The list is closed. Words such as lost, wiped, deleted, skipped and corrupted stay out: "I lost the race to another lane" and "I wiped the cache to reproduce it" are normal work.
- A negator clears the admission only when at most three words sit between it and the fault word. "Nothing I did broke the build" passes. "I did not run the check and broke the build" blocks.
- Quoted and backticked text, fences and URLs are read as text, never as an admission. So a report can quote the owner's words.
- A guard is named when the Deviations item holds `step:<slug>`, the word debt, or a sentence with a guard, check or hook word and a PR or commit ref. A negator near the word debt clears it, as the bullet on debt below says. These words match in any case. It may sit in any bullet of the item. This read keeps backticked text, so `` `step:<slug>` `` counts.
- A guard line labels its guard in any section. The label opens a sentence: `Guard` or `Guards`, then `:`, `—`, `–`, ` - ` or ` -- `, bold or italic or plain. "Missing guard:" is a label too.
- The colon form `Guard:` also counts after a dash, a spaced hyphen, a comma, the word "and" or an opening parenthesis, in any case. The dash form counts only at a sentence start, so "the push guard - refuses it" holds no label.
- From the label to the end of its line, a guard line names a PR or commit ref, `step:<slug>` or a debt. The check reads it with or without an admission. Backticked refs count.
- Owner, 2026-11-12 15:46 CST (item 628 a): a guard line with no reference is refused, with no admission needed. "none", "n/a" and "not needed" get no exemption. A report with no guard to name leaves the line out or names a step.
- Owner, 2026-11-13 18:24 CST (item 700 a): the check finds more label forms. Role subjects stay out until a count exists.
- A guard line's ref is `PR #N` or `/pull/N`, `/commit/<sha>`, a bare `#N` or `PR N` of two or more digits. Or it is a sha of 7 to 40 hex digits with a letter and a digit. "See item #1" is no ref.
- A negator clears the word debt within three words before it or two words after it. So "a debt is not needed" names no debt, and "Debt check-gap filed (not urgent)" names one.
- The refusal names the section that holds the guard line. It never quotes the line.
- `step:<slug>` is checked for its form only. The check does not read the roadmap.
- The check reads only landed turns, as the rest of the report guard does. An admission in a turn that landed nothing is not checked.
- The report guard refuses once per turn. A correction after the refusal is not checked again, as for every other report check.

False-alarm measure, 2026-11-06, on head d96d8821a: 41 real reports with a Deviations item, from 28 cloud sessions. The check refused 2. Both were real mistakes (a wrong commit SHA sent to the batch runner) with no guard named. It had no false alarms. An early draft that matched any first-person verb such as "I ran" or "I pushed", or a bare fault word, fired on 8, of which 3 were false alarms.

## The inbox incident's guard

The lane `state-file-parse-check` (a parse check after each edit to a state file, such as an inbox fence or a JSON file) owns the guard for the inbox incident. This lane does not build it.

Kind: process
Home: rule:building-mistake-names-its-guard
