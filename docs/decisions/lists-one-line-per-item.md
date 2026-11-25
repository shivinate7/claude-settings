# Files that many lanes edit hold one entry per line

## The ruling

A list, table or registry that many lanes add to holds one entry per line.
Where order cannot matter, the lines are sorted.
A list may hold one file per entry instead.
One list has one home, and other places read it.
Record prose holds one sentence per line.
The mistake it stops: two lanes that each add one entry to a one-line list conflict at their merge of main.

## Owner words, 2026-11-25 (CST)

The owner typed these in the consultant's chat. Each is quoted byte for byte with its time.

- 10:07, a question: "are we doing a good job at ensuring files are small and spliced so that agents can take their piece more quicky (kinda how we split decisions into their own files and so many other things rather than keep one log) -- in general i'm wondering if we are best in efficiency at allowing multiple agents to work on the same area at once from different angles? maybe send a plan and refuter through this?"
- 10:19, a ruling on the plan's outcome: "it should be a more outcomes based plan as well ie any repo that pulls in claude settings ought to be able to know how to properly be using files yanno rather than just keeping it all in one area"
- 10:47, a question: "how are we ensuring lines are read and or are organized so properly though?"
- 11:12, a ruling to build: "Oddly, we solved this so long ago for like debts/decisions/notes I feel utilizing slug concepts and stuff like that and stamping upon merge etc etc -- it's shocking to me that despite my echoing of shared best practices across concepts this blunder was made and is likely not the only one there's probably more that we'll need to do.. please build yes -- sonnet workflow imo?"
- 11:12, three short replies: on a tool that prints a file's outline so a session reads one section: "approved"; on a script that ranks conflicted files: "this is so desired"; on a note when a session reads a long file whole: "im open to it".
- 11:15, a ruling: "approved on doign this in claude-settings for the most part, but i also think if there were some way to fail a test when repos install claude-settings and they have this same failure so that way when files they edit next go to merge they see this failure and claude-settings rules on it and kinda just fix, that'd be so awesome, it'd probably be part work in the compliance check skill, part work here -- message sim manager on this conceptual"

## Measured

Two independent agent measures, made on Nov 25, 2026, report these. They are reported, not a test.

- 57 of 308 merges of main into branches conflicted since Nov 18.
- Of 122 conflict hunks, 15 were list lines, 28 were long Markdown lines and 80 were other code.
- The three counts sum to 123, not 122. The source does not say which count is off.
- merge/test_merge.py had 0 conflicts in 42 merges where both sides touched it.

## Consultant picks

The consultant chose these. The owner has not ruled on them.

- No file lease.
- No split of merge/test_merge.py now.
- The list check fires at more than 8 entries on one line, and only on a list that the pull request adds to.
- The list check ships off by default first.

## In flight

Each branch below is in flight. None is built.

- `scope-lists-one-per-line`: scope lists, one entry per line.
- `mutants-one-file-per-rule`: mutants, one file per rule.
- `outline-tool`: prints a file's outline, so a session reads one section.
- `conflict-hotspots`: ranks the files that conflict.
- The list check, on its own branch; the glossary check refuses that branch's slug in an added line, so the slug is held back.
- `ready-checks-one-per-line`: ready checks, one entry per line.
- `guard-file-set-one-manifest`: the guard's file set, in one manifest.
- `record-prose-one-sentence-line`: record prose, one sentence per line.

## Not built

- The compliance-check skill section. It waits for the skills revamp (decision `skill-edits-follow-work`).
- The whole-read note, a note only, inside hooks/reread_check.py --pre-read.
- The big splits: merge/merge.py by concern, merge/test_lane_lint.py, and .github/workflows/checks.yml.

Reason: two lanes that each add one line to a shared one-line list clash at the merge of main. One file per entry means no two lanes edit the same file. The same shape already holds for notes (decision `notes-merge-union`).

Kind: process
Home: lint/check_record_slugs.py
