# Brief: c118, a decision always reaches a pick you can click

Repo: shivinate7/claude-settings, from main b031394f. One lane: builder (sonnet), then reviewer (sonnet).

## Task
A report's Input Needed can hold a pick with options, written as text only. Nothing checks that the pick reached a control the owner can click.
- Extend the Stop report gate, `lint/report_gate.py` (one home; do not add a second Stop hook).
- When the last reply has an Input Needed label that holds a pick with options, the stop passes only when the same turn did one of these:
  1. opened the question box (the AskUserQuestion tool), with nothing of the session's own running; or
  2. wrote the item to the repo's waiting page (an `ArtifactData` `set items/<id>` call to the URL `python3 lint/layout.py waiting-page <root>` prints), and the reply links that page.
- When the repo has no waiting page, case 1 is the only pass. The refusal says what to do in one line, and never names a forbidden target (git-remedy-never-names-target).
- Define "a pick with options" narrowly: lettered or numbered options, or "A or B" under Input Needed. Name the pattern in the code and in the record.

## Rulings
- questions-go-to-owner (CLAUDE.md): with work running, ask in the reply and on the page, never in the box. c84 and c86 already refuse the box while work runs; read them, do not duplicate them.
- verification-cry-wolf-guard-is-spent: an Input Needed with no options (a plain ask) must pass.
- building-guard-needs-incident: the record names the incident: a degen report on Oct 27 put a pick in Input Needed as text, and the owner found it late.

## Failure classes
- A false refusal on Input Needed text that only quotes an earlier answer.
- A pass on a page write to another repo's page.
- A transcript read that misses a tool call in a subagent's lines (read only the main session's turn).

## Check that proves it done
New cases red on main b031394f and green on the branch, in the report gate's test file. Also lint/rule_audit.py, lint/hook_catalog.py --check, lint/test_settings_matcher.py, bin/ste-changed origin/main.

## Report
At most 15 lines: PR, head, red run, green run, review verdict. Send the green, reviewed head to the build advisor. Do not rebase onto main and do not merge.
