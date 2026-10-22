# How a cull runs

## The question

What rules govern a cull of rules, prose, guards, tests and records?

## Ruling

Owner ruling, 2026-10-17 11:56 CDT. The deletion fast path and the notes tier live in `roles-review-cap-three` and `roles-holes-are-debts`. The rest:

- No history in the tree. A decision holds only a ruling in force, plus a one-line reason. One exception (owner, 2026-10-21): raw evidence lives inside the decision or debt that uses it, in an Evidence section of about 10 lines, deleted with that record. Delete a decision that a later one replaced, or that a guard or gate fully enforces with nothing left to say. Add no history section and no "previously" note.
- Prose leaves only with proof. The `lint/rule_mechanisms.json` row names a test, the test case name states the behaviour, and a mutant is killed. Keep a reminder of 3 words or fewer, plus the one-line reason. Check these first: `shared-trees-no-destructive-git`, `shared-trees-no-machine-wide-kill`, `git-never-discard-output`, `git-cite-by-id`, `roles-opus-override-guarded`, `roles-third-try-steps-up`.
- The cull runs first. No file moves or renames during it. The only additions are the prose-proof tests and text a brief names. Time box: Monday 2026-10-19.

Owner answers, 2026-10-17 12:14 CDT:

- Stop after two batches in a row in which debt files and decision files each fall by less than 5%. Hook Python lines need only go down.
- A kept decision is trimmed to its ruling plus a one-line reason. A one-line Kind is added where `lint/check_ruling_kind.py` needs it.
- A test-case rename is allowed for a prose-proof test. The change updates the mutants that name it in the same commit.

Owner answer, 2026-10-17 12:53 CDT: a lane may reword a line when the result has fewer lines and words than before and keeps the current reason. The owner gave no other reason.

## Why

The tree carries more records than a session can read. A cull keeps the rulings in force and drops the rest. The protected outcome: a session finds the current ruling fast, and no stale text misleads it.

Kind: process
Home: rule:speak-rewrite-superseded-in-place
