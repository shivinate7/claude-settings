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
`reviewer-brief-blind`. It goes through `guard_core.refuse()`, so the owner's override lifts it. A report-shape or verdict-line refusal names the refused line by its number, never its text, so it names no forbidden target (rule git-remedy-never-names-target). The unread-prompt refusal names no line.

- A report-shaped block: two or more of the report labels (Done, Deviations, Input Needed, Next) at line
  start, or a BUILT or RECORDED item at line start, with or without a `Done:` label before it.
- A verdict line: a line with `verdict`, or a round label with or without `result`, before its colon,
  and a reviewer verdict word right after the colon. A report's leading verdict, `FAIL, round 2`, is one too.
  The verdict words are one constant in `hooks/guard.py`. The scan also reads these forms:
  - Marks right after a colon are dropped: `**Verdict:** FAIL` is refused.
  - A dash after a round label reads as the colon: `Round 2 - FAIL` is refused.
  - After `verdict`, a dash reads as the colon if a space or an em or en dash comes first:
    `Prior verdict - FAIL` and `Prior verdict—FAIL` are refused. An unspaced hyphen does not: `Prior verdict-FAIL` passes.
  - `round result` reads as a verdict label: `Prior round result: FAIL` is refused.
  - A report label (`Done:`, `Deviations:`, `Input Needed:`, `Next:`) followed by a bare verdict word that ends its clause reads as a verdict line: `Done: FAIL.` is refused. A choice list does not: `Next: PASS or FAIL` passes.
  - One short label of one to four words, such as `Done:` or `Prior review:`, may come before a verdict shape.
    A label of five or more words passes, as in `Prior review of the diff: verdict: FAIL`. A `verdict` or
    `round result` in the label still refuses.
- A report shape counts at line start only. A verdict label counts anywhere in its sentence before
  the colon. The check matches shapes, never words: a brief that quotes the task's words ("never
  holds the builder's report or a prior verdict") passes.
- Before the match, each backtick span is blanked unless it holds only a verdict word. Each line is
  split into sentences. A choice list of verdict words that ends its sentence is blanked. So a
  line that only names the verdict format passes: `End your report with a verdict: PASS, FAIL or
  PARTIAL.`
- The role set is one constant: `reviewer`, and the refuter, the agent that argues back (owner, item
  282, pick b, 2026-11-06). The refuter's name has one home, `REFUTER_ROLE` in `hooks/guard_core.py`
  (decision plan-refuter), and `hooks/guard.py` imports it.

Not caught: a builder's argument pasted as prose, with no label or verdict line. Rule
`roles-resume-by-name` and `agents/reviewer.md` cover it in words. A report relayed to a running
reviewer by SendMessage is not checked.
- A Workflow agent() reviewer prompt the scan cannot read, such as a variable or a template with
  `${...}`, is refused with its own reason: the guard could not read the brief, so write it as a literal
  string. A workflow passes work to a reviewer as a file the reviewer reads (owner item 299, pending;
  built as the page's recommended pick b).
- A report label may carry Markdown marks before it (`-`, `*`, `#`, bold). A verdict word counts only right
  after a colon, or a dash that reads as one, with marks or quotes allowed between. So `Round N of 3: check PASS
  or FAIL` passes. A line that opens with a verdict word and a colon, such as `PASS: the diff fixes the finding`
  or `FAIL: test_x`, is a quote, so it passes.

Mistake it stops: an orchestrator pastes the builder's report, or a prior round's verdict, into a reviewer's
brief. Harm: the review confirms instead of hunting, and the review round adds no safety.

Cost: no process start and no file written. It runs inside the guard.py start each Agent, Task or
Workflow call already makes, and writes the guard.log line of a refusal only.

Kind: process
Home: hooks/guard.py
