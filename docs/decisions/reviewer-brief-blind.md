# A reviewer's brief holds no report or verdict

## The ruling

Owner, waiting-page item 279, pick a, 2026-11-06 12:43 CST. A debate-coverage audit found that a reviewer
brief can carry the builder's report or a prior round's verdict. A reviewer that reads it anchors on it
and confirms it, so a defect the builder argued past reaches main.

- A reviewer's brief holds the task brief, the diff or a pointer to it, and the governing rulings. It
  never holds the builder's report, the builder's reasoning, or a prior round's verdict.
- A later round, or a fresh reviewer for a lane that has no finished agent to replace, gets the prior
  round's findings as a list to check: file, line and claim. It never gets that round's verdict or argument.
- A fresh agent that replaces a finished one of the same role may carry the prior report. Its brief's
  first non-blank line is `Replaces: <name>`, the name of the agent it replaces. Owner, waiting-page item
  409 a, 2026-11-08 06:11 CST: when a finished agent's worktree is gone, a fresh agent of the same role
  gets the prior report. The coordinator relayed it for this guard on 2026-11-12 10:55 CST.
- A fix check gets the named finding it checks. That is a finding list, so it passes.

## The check

`hooks/guard.py` refuses an Agent or Task spawn, and each Workflow agent() call, whose role is a
reviewer and whose brief holds a report-shaped block or a verdict line. The rule is
`reviewer-brief-blind`. It goes through `guard_core.refuse()`, so the owner's override lifts it.

- A report-shaped block is one of two shapes. Two or more of the report labels (Done, Deviations, Input
  Needed, Next) at line start, each with a body (text after it, or a non-label line under it). Or a BUILT
  or RECORDED item at line start, with or without a `Done:` label before it. A bare label list, such as `Report with:` and then
  `- Done`, `- Deviations`, asks for a report's shape and passes.
- A verdict line begins at line start and takes one of three forms. A line with the word `verdict`
  anywhere before its colon. A round label (`Round 1`, `Prior round`) before a colon or a dash, with or
  without `result`. Both need a reviewer verdict word right after the separator, bold marks allowed. Or a
  report's leading verdict, `FAIL, round 1 of 3, ...`, bare or after `Done:`. A choice list, `Verdict: PASS
  or FAIL`, is a request and passes. The verdict words are one constant in `hooks/guard.py`.
- Every shape starts at a line start, so a brief that quotes the task's words ("never holds the builder's
  report or a prior verdict") passes. The word `verdict` itself is read anywhere in that line before the
  colon, not only at its start.
- The role set is one constant: `reviewer`, and the refuter, the agent that argues back (owner, item
  282, pick b, 2026-11-06). The refuter's name has one home, `REFUTER_ROLE` in `hooks/guard_core.py`
  (decision plan-refuter), and `hooks/guard.py` imports it.

The `Replaces:` line lifts the report and verdict refusals for a reviewer or refuter brief, in Agent, Task and a
Workflow agent() call with a literal prompt. The marker is case-sensitive and must open the first non-blank
line. A marker on a later line lifts nothing. An empty or blank name lifts nothing. A builder brief is outside
the guarded roles, so the marker changes nothing for it. A Workflow prompt with a `${...}` template stays
unread and refused, marker or not. The marker's text is `REPLACES_MARKER` in `hooks/shared_names.py`, which
`hooks/guard.py` imports.

The marker form is this lane's pick. The owner ruled only that a replacement gets the prior report. The pick
is undoable. The guard cannot check that the named agent exists. A copied marker over a pasted report passes.
It is a mistake-guard, not a wall (`guard-guards-mistakes-only`).

Not caught: a builder's argument pasted as prose, with no label or verdict line. Rule
`roles-resume-by-name` and `agents/reviewer.md` cover it in words. A report relayed to a running
reviewer by SendMessage is not checked.
- A Workflow agent() reviewer prompt the scan cannot read, such as a variable or a template with
  `${...}`, is refused with its own reason (choice b, which stands: owner item 299 is settled as pick c,
  owner note of 2026-11-06): the guard could not read the brief, so write it as a literal
  string. The refusal tells the author to name the diff file or the commit range in the brief, not its
  contents. The guard cannot read a file a reviewer opens, so a file route is not checked.
- A report label may carry Markdown marks before it (`-`, `*`, `#`, bold). The verdict word must sit
  right after the colon, so `Round 2 of 3: check PASS or FAIL` passes. A line that opens with a verdict
  word and a colon, such as `PASS: the diff fixes the finding` or `FAIL: test_x`, is a quote, so it passes.

Mistake it stops: an orchestrator pastes the builder's report, or round 1's verdict, into a reviewer's
brief. Harm: the review confirms instead of hunting, and the review round adds no safety.

Cost: no process start and no file written. It runs inside the guard.py start each Agent, Task or
Workflow call already makes, and writes the guard.log line of a refusal only.

Kind: process
Home: hooks/guard.py
