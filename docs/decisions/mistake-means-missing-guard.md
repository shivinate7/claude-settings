# A mistake Claude made means a guard is missing

## Ruling

Owner, 2026-11-06 11:38 CST: AI sometimes assumes it broke something by accident. The way we work should make accidents hard, so a mistake is a strong sign, not a certainty, that a guard belongs there. Owning up to the mistake does not close the problem.

- The report names the guard that would have stopped the mistake: built (a PR or commit), queued as `step:<slug>`, or a debt.
- An apology alone is not a fix.

Incident, 2026-11-06: the coordinator ran `sed -i '$d'` on its feedback inbox to drop the last item. The command deleted the closing code fence instead. Only the Stop check in `hooks/feedback_guard.py` caught it, one turn later. The same day, the coordinator trusted a stale decision line and called a lane idle while the lane's PR was open.

## The check

`lint/report_guard.py` refuses a report on a landing turn whose Deviations item admits a mistake you made and names no guard for it.

- An admission is a clause with a first-person word (`I`, `my`) and a fault word, such as wrong, mistake, broke, clobbered, overwrote, misread, forgot, trusted or "instead of checking".
- A negator before the fault word in the same clause clears it: "I did not break anything" passes.
- Quoted and backticked text, fences and URLs are read as text, never as an admission. So a report can quote the owner's words.
- A guard is named when the Deviations item holds `step:<slug>`, the word debt, or a guard, check or hook word together with a PR or commit ref.
- `step:<slug>` is checked for its form only. The check does not read the roadmap.
- The check reads only landing turns, as the rest of the report guard does. An admission in a turn that landed nothing is not checked.

False-alarm measure, 2026-11-06: 41 real reports with a Deviations item, from 28 cloud sessions. The check fired on 2. Both were real mistakes (a wrong commit SHA sent to the batch runner) with no guard named. It had no false alarms. A wider set that read bare "wrong", "mistake" and verbs such as "I ran" or "I pushed" fired on 8, of which 3 were false alarms.

## Proposed: an inbox fence check at the edit

The incident's own guard, queued as `step:inbox-fence-check`. It is not built.

- A PostToolUse hook on Bash, Edit and Write. A shell pre-filter exits unless the tool input names `.inbox.md`, so most tool calls start no Python process.
- When it runs, it reads the session's inbox file with the block and fence parser in `hooks/feedback_guard.py`. It blocks when a fence is left open, and names the file and the line.
- Cost: one shell start per Bash, Edit or Write call. One Python start and one file read per call that names the inbox. It writes no file.

Kind: process
Home: rule:building-mistake-names-its-guard
