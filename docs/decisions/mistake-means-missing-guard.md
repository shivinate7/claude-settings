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

`lint/report_guard.py` refuses a report on a landed turn whose Deviations item admits a mistake you made and names no guard for it.

- An admission is a clause with a first-person word (`I`, `my`) before a fault word. Clauses split at punctuation and at because, since, but, while and although. "The test was wrong so I re-pointed it" passes.
- The fault words: wrong, wrongly, mistake, mistaken, by accident, accidental, accidentally, broke, clobbered, overwrote, misread, forgot, "trusted a stale", "trusted an old", "trusted an outdated" and "instead of checking". The list is closed. Words such as lost, wiped, deleted, skipped and corrupted stay out: "I lost the race to another lane" and "I wiped the cache to reproduce it" are normal work.
- A negator clears the admission only when at most three words sit between it and the fault word. "Nothing I did broke the build" passes. "I did not run the check and broke the build" blocks.
- Quoted and backticked text, fences and URLs are read as text, never as an admission. So a report can quote the owner's words.
- A guard is named when the Deviations item holds `step:<slug>`, the word debt, or a sentence with a guard, check or hook word and a PR or commit ref. These words match in any case. It may sit in any bullet of the item. This read keeps backticked text, so `` `step:<slug>` `` counts.
- `step:<slug>` is read from git (owner, 2026-11-12 12:11 CST, "mechanize the verification that something was queued"). A report that cites a step, in Deviations or in a sentence that says queued, filed or has a step, passes only when `roadmap/data/steps/<slug>.json` is a blob on `origin/roadmap`. A step only on a lane branch is not queued. A sentence that claims a step is queued or filed and names no `step:<slug>` is refused. A claim ties a roadmap word to the step noun: queued or filed as a step, or the step is queued. Added counts with roadmap or queue in the step's clause. Has a step counts with roadmap, follow-up, guard or fix in its clause. A slug in a negated or future claim (not yet filed, will file, File step:x) is no claim. "Queued" in other senses (a CI run, a job, a merge queue, a lane waiting), a step in coding text (a script's step, the deploy step) and quoted or backticked text make no claim. An unbacked sentence and a missing slug share one refusal. The report cite calls `ruling_home.step_filed`; the feedback inbox check reaches the same read, `ruling_home.blob_held`, through `value_resolves`.
- Cost: one `git fetch origin roadmap` and one tree read per report that cites a step; none for a report that cites none. A failed fetch or read prints `unknown` and refuses nothing.
- Incident, 2026-11-12 12:10 CST: the coordinator reported a guard as queued as `step:pick-reaches-page`. No step file existed on `origin/roadmap`; triage had not filed it. Harm: the owner trusted a guard that was in no queue. Tests: `lint/test_report_guard_steps.py`.
- The check reads only landed turns, as the rest of the report guard does. An admission in a turn that landed nothing is not checked.
- The report guard refuses once per turn. A correction after the refusal is not checked again, as for every other report check.

False-alarm measure, 2026-11-06, on head d96d8821a: 41 real reports with a Deviations item, from 28 cloud sessions. The check refused 2. Both were real mistakes (a wrong commit SHA sent to the batch runner) with no guard named. It had no false alarms. An early draft that matched any first-person verb such as "I ran" or "I pushed", or a bare fault word, fired on 8, of which 3 were false alarms.

## The inbox incident's guard

The lane `state-file-parse-check` (a parse check after each edit to a state file, such as an inbox fence or a JSON file) owns the guard for the inbox incident. This lane does not build it.

Kind: process
Home: rule:building-mistake-names-its-guard
