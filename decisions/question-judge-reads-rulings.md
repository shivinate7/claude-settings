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
  question. The record id is `<dir>/<stem>` (the path minus `.md`), so a `decisions/` and a
  `deferred/` record with one stem stay apart (the orchestrator's call, 2026-10-17). The deny
  reason gives the record id and title, and no `.md` file. An id the hook did
  not show the model is not cited.
- Each ruling is cut to `RULING_CAP` (800 chars) at a sentence end, and a mark shows the cut.
  The rulings section adds at most `RULINGS_MAX` (60,000 chars) to the prompt. Records come
  newest first from one `git log` call (0.50 s measured); file mtime orders them only when git
  fails or does not list a file. When the records hold more, the oldest are left out and the
  section says how many. A record with no H1 title shows as "untitled".
- Split between "settled" and "asks to change a ruling": the model makes it, from the intro
  text beside `PROMPT`. No test proves that split.

Kind: process
Home: hooks/question_outcome.py

## Holes, named

Debts: `judge-cap-drops-old-rulings` (the 60,000-char cap leaves out the oldest rulings). `judge-cuts-long-ruling` (a ruling over 800 chars is cut, so a late point may be missed). `judge-uncommitted-order` (an uncommitted record sorts after the listed ones). `judge-skips-other-headings` (rulings under another heading are not read). `judge-heading-false-match` (the heading pattern matches "Ruling out" headings).
