# A reviewer's brief holds no report or verdict

## The ruling

Owner, waiting-page item 279, pick a, 2026-11-06 12:43 CST. A debate-coverage audit found that a reviewer
brief can carry the builder's report or a prior round's verdict. A reviewer that reads it anchors on it
and confirms it, so a defect the builder argued past reaches main.

- A reviewer's brief holds the task brief, the diff or a pointer to it, and the governing rulings. It
  never holds the builder's report, the builder's reasoning, or a prior round's verdict.
- A later round, or a fresh reviewer after a dead one, gets the prior round's findings as a list to
  check: file, line and claim. It never gets that round's verdict or argument.
- A fix check gets the named finding it checks. That is a finding list, so it passes.

## The check

`hooks/guard.py` refuses an Agent or Task spawn, and each Workflow agent() call, whose role is a
reviewer and whose brief holds a report-shaped block or a verdict line. The rule is
`reviewer-brief-blind`. It goes through `guard_core.refuse()`, so the owner's override lifts it.

- A report-shaped block: two or more of the report labels (Done, Deviations, Input Needed, Next) at line
  start, or a BUILT or RECORDED item at line start.
- A verdict line: a line that opens with `Verdict:` or a round label and carries a reviewer verdict word.
  The verdict words are one constant in `hooks/guard.py`.
- The check matches shapes at line start, never words. A brief that quotes the task's words ("never
  holds the builder's report or a prior verdict") passes.
- The role set is one constant: `reviewer`, and the term for an agent that argues back. That term is one
  constant in `hooks/guard.py`, `challenger` until the owner picks the glossary word (step
  debate-glossary-word). The pick is a one-line rename.

Not caught: a builder's argument pasted as prose, with no label or verdict line. Rule
`roles-resume-by-name` and `agents/reviewer.md` cover it in words. A report relayed to a running
reviewer by SendMessage is not checked.

Mistake it stops: an orchestrator pastes the builder's report, or round 1's verdict, into a reviewer's
brief. Harm: the review confirms instead of hunting, and the review round adds no safety.

Cost: no process start and no file written. It runs inside the guard.py start each Agent, Task or
Workflow call already makes, and writes the guard.log line of a refusal only.

Kind: process
Home: hooks/guard.py
