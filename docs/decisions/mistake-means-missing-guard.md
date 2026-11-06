# A mistake Claude made means a guard is missing

## Ruling

Owner, 2026-11-06 11:38 CST: AI sometimes assumes it broke something by accident. The way we work should make accidents hard, so a mistake is a strong sign, not a certainty, that a guard belongs there. Owning up to the mistake does not close the problem.

- The report names the guard that would have stopped the mistake: built (a PR or commit), queued as `step:<slug>`, or a debt.
- An apology alone is not a fix.

Incident, 2026-11-06: the coordinator ran `sed -i '$d'` on its feedback inbox to drop the last item. The command deleted the closing code fence instead. Only the Stop check in `hooks/feedback_guard.py` caught it, one turn later. The same day, the coordinator trusted a stale decision line and called a lane idle while the lane's PR was open.

More incidents, 2026-11-06, from the batch of PR #1034 (a batch of lanes), each with the guard it lacked. Neither guard is built.

- A suggested fix, a `.gitkeep` exclude, was pushed without a run of the repo's own code check, which then refused it. Missing guard: run the repo's own checks on a suggested fix before the push.
- A lane's new CI job was proven only locally, where its tools resolve. In CI the job could not load a dependency. Missing guard: a new CI job gets one CI run of its own before it joins a batch.

## The check

`lint/report_guard.py` refuses a report on a landing turn whose Deviations item admits a mistake you made and names no guard for it.

- An admission is a clause with a first-person word (`I`, `my`) and a fault word. Clauses split at punctuation and at because, since, but, while and although.
- The fault words: wrong, wrongly, mistake, mistaken, by accident, accidental, accidentally, broke, clobbered, overwrote, corrupted, misread, forgot, "trusted a stale", "trusted an old", "trusted an outdated" and "instead of checking". The list is closed. Words such as lost, wiped, deleted and skipped stay out: "I lost the race to another lane" and "I wiped the cache to reproduce it" are normal work.
- A negator before the fault word in the same clause clears it: "I did not break anything" passes.
- Quoted and backticked text, fences and URLs are read as text, never as an admission. So a report can quote the owner's words.
- A guard is named when the Deviations item holds `step:<slug>`, the word debt, or a sentence with a guard, check or hook word and a PR or commit ref. It may sit in any bullet of the item. This read keeps backticked text, so `` `step:<slug>` `` counts.
- `step:<slug>` is checked for its form only. The check does not read the roadmap.
- The check reads only landing turns, as the rest of the report guard does. An admission in a turn that landed nothing is not checked.
- The report guard blocks once per turn. A correction after the block is not checked again, as for every other report check.

False-alarm measure, 2026-11-06: 41 real reports with a Deviations item, from 28 cloud sessions. The check fired on 2. Both were real mistakes (a wrong commit SHA sent to the batch runner) with no guard named. It had no false alarms. A wider set that read bare "wrong", "mistake" and verbs such as "I ran" or "I pushed" fired on 8, of which 3 were false alarms.

## Proposed: an inbox fence check at the edit

The incident's own guard, queued as `step:inbox-fence-check`. It is not built.

- A PostToolUse hook on Bash, Edit and Write. A shell pre-filter exits unless the tool input names `.inbox.md`, so most tool calls start no Python process.
- When it runs, it reads the session's inbox file with the block and fence parser in `hooks/feedback_guard.py`. It blocks when a fence is left open, and names the file and the line.
- Cost: one shell start per Bash, Edit or Write call. One Python start and one file read per call that names the inbox. It writes no file.

Kind: process
Home: rule:building-mistake-names-its-guard
