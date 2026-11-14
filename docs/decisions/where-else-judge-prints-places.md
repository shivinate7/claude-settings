# The merge asks where else a landed ruling applies

## The ruling

When a pull request lands a ruling, rule or guard, the merge tool asks the model once where else in the repo the same mistake class or principle applies. It prints each answer as one candidate line. Triage is the only writer of steps: it reads the printed lines and decides. The judge refuses nothing, changes no exit status and writes no file.

Lands means that the range adds or changes one of three things (read merge/merge.py where_else_landed):

- A decision record under the decisions folder that the range adds. An edit of an existing record counts only at `WHERE_ELSE_MIN_EDIT_LINES` (5) or more changed lines, added plus removed.
- A `<!-- rule:slug -->` anchor sentence in a rule file that is new or differs from the base's (read lint/rule_audit.py RULE_FILES).
- A rule name that is new, or has a source line the base lacks. A guard module passes it to `refuse()`, `record()` or `ask_command()`, or the `diff_rule` table or the role-scope table lists it (read lint/rule_audit.py guard_rule_names).

Why: a ruling that fixes one mistake leaves the same mistake in other places, and today nobody asks. The claim-at-merge rule (`git-slug-then-claim-number`) names records. Guard section files are numbered too, and no one asked whether they mint numbers on a branch.

## Why it extends the prose judge

It is not a second judge. It sits in `merge/merge.py` beside the prose judge, plans under the lock and runs after the lock is released, and calls the one model path, `decision_watch.invoke_model` (read merge/merge.py where_else_plan; read merge/merge.py where_else_run). It reuses the prose judge's failure buckets through `prose_judge_cause`, and `lint/rule_audit.py` for the anchor form, the rule files, the guard module list and the guard rule names. Only the question and the reply shape differ: `PLACES` in `hooks/decision_watch.py` reads a list of `{path, section, why}` (read hooks/decision_watch.py PLACES). The prose judge asks per line whether a line holds, so the same call cannot answer this question.

## What it prints

- One line per place the model names, at most 10, then one count line. Each says "candidate, not a finding" and that model verdicts vary run to run. A `section` the model gives as a string of digits prints like a number.
- A failure prints one `where-else UNKNOWN` line naming its bucket: timed out, model error or no readable verdict. It never reads as clear (read merge/merge.py where_else_run).
- The prompt says that other repos are not attached and unread. A place in another repo stays unknown until a repo is attached.
- The prompt carries the guard section files, each with its first line. The model can name a section number only from there (read merge/merge.py where_else_evidence). The folder is the one the guard runner names, read by `section_dir` in `lint/rule_audit.py`.

## Caps

- The prompt holds at most `WHERE_ELSE_MAX_RECORDS` (10) decision records and at most `WHERE_ELSE_MAX_CHARS` (30000) characters. Each landed text is cut to its share of what the fixed parts leave (read merge/merge.py where_else_prompt).
- A range with more records than that judges the first 10 by path and prints one line: "too many records, judged first 10, N not judged". The cap never goes silent.
- The plan reads a path only when the path's kind needs it: two `git diff` calls cover every decision record, and one `git show` per rule or guard file that the range changed.

## The cost

One model call per merge that lands a ruling, rule or guard. No call otherwise. No new process, timer or log, and no file written.

How often (candidate count, GitHub REST not used). The count is merges on main by first parent, and a landing is what the trigger above reads in each merge's base and head.

- Full history, 30 days (2026-10-14 to 2026-11-13, a blobless clone made for the count on a scratch path): 321 merges. 180 land by the trigger above, about 6 calls a day. 229 touch a decision, a rule file or a guard module at all. That any-touch count is the trigger as first built, and it would have made about 8 calls a day.
- This clone is shallow. Its first-parent history starts 2026-11-07, so it covers 7 days: 78 merges, 59 touches, 46 landings (about 7 calls a day).

Command: `git log main --first-parent --since="2026-10-14" --format="%H %cs"`, then for each merge `git diff --name-only --no-renames -z <merge>^1 <merge>`, a `--numstat` of the records, and the anchor and guard reads of the trigger above.

Unmeasured: how often a printed candidate is right. The first reader is triage.

Kind: process
Home: merge/merge.py
