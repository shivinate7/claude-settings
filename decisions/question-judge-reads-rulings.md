# The question judge refuses a question the owner already settled

## The ruling

The question judge (question-outcome-check) reads the repo's decision and deferred records and refuses a
question the owner already settled. A question that asks to change a ruling is allowed.

- The repo is the `cwd` of the hook payload. The hook reads `decisions/*.md` and `deferred/*.md` under it.
- A decision's ruling is each H2 section titled "The ruling", "Ruling", "The rulings" or "The owner's
  rulings" (any suffix), to the next H2 outside a code fence. A deferred record's ruling is its
  "**Why it waits.**" paragraph. A ruling under any other heading is not read, so a record holds its
  ruling under a Ruling heading.
- Each ruling is fenced like conversation text and labeled with its record id and H1 title, so ruling
  text cannot forge an owner block.
- The model replies `{"verdict": "FLAG", "record": "<id>", "why": ...}` for a settled question. A record
  id is `<folder>/<stem>` (for example `decisions/bare-merge-asks`), so a decision and a deferred record
  with one stem do not collide. The deny reason gives the id and title, with no absolute path. An id the
  hook did not show the model is not cited.
- Each ruling is cut to `RULING_CAP` (800 chars) at a sentence end, and a mark shows the cut. The
  rulings section adds at most `RULINGS_MAX` (60,000 chars) to the prompt. Records come newest first from
  one `git log` call. File mtime orders them only when git fails or does not list a file. When the
  records hold more, the oldest are left out and the section says how many. A record with no H1 title
  shows as "untitled".
- The model makes the split between "settled" and "asks to change a ruling", from the intro text beside
  `PROMPT`. No test proves that split.

Reason: the owner kept being asked a question a record already answers, because the judge read only the
conversation.

Kind: process
Home: hooks/question_outcome.py

## Holes, named

Debts: `judge-cap-drops-old-rulings`.
