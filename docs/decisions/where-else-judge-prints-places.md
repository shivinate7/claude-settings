# The merge asks where else a landed ruling applies

## The ruling

When a pull request lands a ruling, rule or guard, the merge tool asks the model once where else in the repo the same mistake class or principle applies. It prints each answer as one candidate line. Triage is the only writer of steps: it reads the printed lines and decides. The judge refuses nothing, changes no exit status and writes no file.

Lands means the range adds or changes one of three things. A record under the decisions folder. A `<!-- rule:slug -->` anchor sentence in a rule file. A rule name that `hooks/guard*.py` passes to `refuse()`, `record()` or `ask_command()` (read merge/merge.py where_else_landed; read lint/rule_audit.py guard_rule_names).

Why: a ruling that fixes one mistake leaves the same mistake in other places, and today nobody asks. The claim-at-merge rule (`git-slug-then-claim-number`) names records. Guard section files under `tests/guard/` are numbered too, and no one asked whether they mint numbers on a branch.

## Why it extends the prose judge

It is not a second judge. It sits in `merge/merge.py` beside the prose judge, plans under the lock and runs after the lock is released, and calls the one model path, `decision_watch.invoke_model` (read merge/merge.py where_else_plan; read merge/merge.py where_else_run). It reuses the prose judge's failure buckets through `prose_judge_cause`, and `lint/rule_audit.py` for the anchor form, the rule files and the guard rule names. Only the question and the reply shape differ: `PLACES` in `hooks/decision_watch.py` reads a list of `{path, section, why}` (read hooks/decision_watch.py PLACES). The prose judge asks per line whether a line holds, so the same call cannot answer this question.

## What it prints

- One line per place the model names, at most 10, then one count line. Each says "candidate, not a finding" and that model verdicts vary run to run.
- A failure prints one `where-else UNKNOWN` line naming its bucket: timed out, model error or no readable verdict. It never reads as clear (read merge/merge.py where_else_run).
- The prompt says that other repos are not attached and unread. A place in another repo stays unknown until a repo is attached.
- The only other number-minting evidence the prompt carries is the guard section files, each with its first line. The model can name a section number only from there (read merge/merge.py where_else_evidence). The section directory and its name are a copy of `SECTION_DIR` in `hooks/test_guard.py`, because that file runs the whole suite when imported.

## The cost

One model call per merge that lands a ruling, rule or guard. No call otherwise. No new process, timer or log, and no file written.

How often (candidate count, GitHub REST not used): 59 of the 76 first-parent merges on origin/main in the last 30 days touched `docs/decisions/`, `CLAUDE.md`, `output-styles/` or `hooks/guard*.py`. A touch is more than a landing, so 59 is an upper bound on the calls. Command: `git log origin/main --first-parent -m --since="30 days ago" --name-only --format="tformat:@@@%H"`, then count the groups with one of those path prefixes.

Unmeasured: how often a printed candidate is right. The first reader is triage.

Kind: process
Home: merge/merge.py
