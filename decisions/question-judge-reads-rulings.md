# The question judge refuses a question the owner already settled

## The problem

The owner kept being asked a question a record already answers. The question judge (decision
question-outcome-check, each question passes an outcome check first) read only the
conversation, so it could not see a ruling made in an earlier session.

## The ruling

Owner ruling, 2026-10-12 22:10 CDT: the question judge reads the repo's decision and
deferred records and refuses a question the owner already settled. A question that asks to
change a ruling is allowed.

- The repo is the `cwd` of the hook payload. The hook reads `decisions/*.md` and
  `deferred/*.md` under it.
- A decision's ruling is each H2 section titled "The ruling", "Ruling", "The rulings" or
  "The owner's rulings" (any suffix), to the next H2 outside a code fence. A deferred
  record's ruling is its "**Why it waits.**" paragraph. A ruling under any other heading is
  not read, so a record holds its ruling under a Ruling heading.
- Each ruling is fenced like conversation text and labeled with its record id and H1 title,
  so ruling text cannot forge an owner block.
- The model replies `{"verdict": "FLAG", "record": "<id>", "why": ...}` for a settled
  question. The deny reason gives the record id and title, and no path. An id the hook did
  not show the model is not cited.
- The rulings section adds at most `RULINGS_MAX` (30,000 chars) to the prompt. When the
  records hold more, the most recently changed files come first (file mtime) and the rest are
  left out. The section carries a mark when any are left out.
- Split between "settled" and "asks to change a ruling": the model makes it, from the intro
  text beside `PROMPT`. No test proves that split.

Kind: process
Home: hooks/question_outcome.py

## Holes, named

- File mtime orders the records. A fresh checkout gives every file the same time, so the
  order there is by name. Git history would order them better, and costs one call per read.
- A ruling that is itself over `RULINGS_MAX` is left out, not cut.
- Rulings under another heading are not read.
