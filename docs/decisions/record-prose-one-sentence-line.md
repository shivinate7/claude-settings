# A decision record holds one sentence per line

## The ruling

A line that a branch adds to a decision record is one sentence, or it is 200 characters or fewer.
`lint/check_record_slugs.py` refuses a longer line that holds more than one sentence.
The refusal names the file and the line number.

Owner, 2026-11-25 11:12 CST, on the plan to fix the merge conflicts in long lists: "please build yes -- sonnet workflow imo?"

Which lines it reads.
- Only a line the branch adds: a line whose count at head is over its count at the merge base, as the notes check counts a note line (decision `notes-merge-union`).
  An old long line that the branch leaves alone, moves or renames with its file is never judged.
  A line edited in place is an added line.
- Only a file in the decisions folder of `lint/layout.json`. A debt, a note or another doc is not read.
- Only in diff mode: given file arguments, the check reads no git and skips this rule.

What is exempt.
- A heading, a table row, a line inside fenced code, a one-sentence list item and a line that is one quote.
  A quote is the whole line between straight or curly quote marks, bare or after `> `.
  A line of prose around a quote is judged as prose.

How it splits sentences.
- It calls `split_sentences` in `lint/ste_lint.py`, the one splitter. It builds no second one.
- That splitter keeps "e.g.", "i.e.", a version number and a file name such as merge.py whole.
  The check does the following itself, so the pins that child repos hold on `lint/ste_lint.py` do not move.
  A stop inside an inline code span is no sentence end.
  A month abbreviation before a day number is no sentence end, as in "Nov. 25".
  It covers Jan, Feb, Mar, Apr, Jun, Jul, Aug, Sep, Sept, Oct, Nov and Dec, not May.
  The splitter alone breaks such a dot today.
  The dot in etc. or No. ends a sentence when a capital word follows it.
  A stop inside a quote is no sentence end, except one right before the closing mark.
  A quote pairs only within one line.
  A straight quote pairs when its opening mark follows no word character and its closing mark is not followed by a word character; a curly pair needs no such check.
  A line with a triple-backtick code span that closes on the same line opens no fence.

Why: the repo's practice is one entry per line, sorted, in one home (decision `one-layout-every-repo`).
A ruling kept on one long line breaks that practice: two lanes that add a sentence to it add the same line, and git reports a conflict.
Merges of main into lane branches conflicted, and the rate is unmeasured.
Decision `lanes-run-no-full-ci-job` held its ruling as one long line, which also conflicted in merges.

Mistake it guards: a lane adds a sentence to a long ruling line, and the next lane that does the same cannot merge without a hand fix.

Named limits.
- The check judges only lines a branch adds or edits, so a record keeps its old long lines until a lane touches them.
- Counted 2026-11-25, 2,130 existing lines in 235 of 269 decision records would be refused if added fresh.
- None is refused today.
- This lane rewrites `docs/decisions/lanes-run-no-full-ci-job.md`, so an open PR that edits that file will conflict with it.
- A list item of two sentences is refused, so split it into one sentence per line.
- A quote of several sentences on one line is not refused, since its inner stops are no sentence end.
- A quote that runs past its line pairs on no line, so each stop in it ends a sentence.
- A double quote inside a code span can pair with a lone one outside it, which hides the stops between them.
- A curly closing quote with no opening mark on its line is ignored.
- The abbreviations p.m., Inc. and et al. before a capital word count as one sentence, so a sentence after them is missed.
- An ellipsis followed by a lowercase word splits the text in two.
- A No. before a capital word always ends a sentence, so a name such as No. Smith counts as two.

Cost: no process, timer or file added.
In diff mode `added_line_numbers` in `check_record_slugs.py` runs one `git show` of head for each decision record the branch touches, one more at the merge base for each that it edits or renames, and one `git merge-base` when any exists (unmeasured, not pinned by a test).

Kind: process
Home: lint/check_record_slugs.py
