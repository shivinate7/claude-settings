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
  The check also keeps a month abbreviation before a day number whole, as in "Nov. 25", which the splitter breaks today.
  It also keeps a stop inside an inline code span whole.
  The check does both itself, so the pins that child repos hold on `lint/ste_lint.py` do not move.

Why: the repo's practice is one entry per line, sorted, in one home (decision `one-layout-every-repo`).
A ruling kept on one long line breaks that practice: two lanes that add a sentence to it add the same line, and git reports a conflict.
Merges of main into lane branches conflicted, and the rate is unmeasured.
Decision `lanes-run-no-full-ci-job` held its ruling as one long line, which also conflicted in merges.

Mistake it guards: a lane adds a sentence to a long ruling line, and the next lane that does the same cannot merge without a hand fix.

Named limits.
- A record that ships with old long lines keeps them until a lane touches a line.
  The check never rewrites an old line.
- A list item of two sentences, or an `Owner: "..."` line with a quote of several sentences, is refused.
  Split it, with the quote marks open across the lines.
- The check judges sentence count by the STE splitter, with the stops inside an inline code span hidden.
  A stop inside a quote that spans several lines still ends a sentence.

Cost: no process, timer or file added.
In diff mode `added_line_numbers` in `check_record_slugs.py` runs one `git show` of head for each decision record the branch touches, one more at the merge base for each that it edits or renames, and one `git merge-base` when any exists (unmeasured, not pinned by a test).

Kind: process
Home: lint/check_record_slugs.py
