# c86: a check refuses a question box while the session's own work runs

Cloud build thread brief. Build advisor (7), Oct 27, against claude-settings main e305bdb or newer.
claude-settings only. Never rebase onto main after review. Send the green, reviewed head to the
build advisor ("Advise the claude-settings build", read the roster in the project instructions);
never merge.

## Goal

Rule questions-go-to-owner (c84, PR 648, on main) says: while an agent, a lane or a background
command of this session runs, or starts in the same response, never open a question box. Make a
machine hold it: refuse AskUserQuestion while this session has a live agent or background command.

## Inputs

- Incident: Oct 26, a UI session waited on a question box while its background agents filled the
  disk and crashed it. Record it in the guard rule's record (building-guard-needs-incident).
- Debt question-box-while-work-runs (docs/debts) holds the gap. Close it in the same PR.
- The only reader of live agents today is the host agent list that the session-board mod reads.
  Find how it reads that list, and read the same source from a PreToolUse hook on AskUserQuestion.
  If no source a hook can read exists, stop and report that as a finding with what you measured.
- Rule outcomes-mechanize-rules: read on demand inside the hook only, no timer, no watcher, no new
  long-lived process. State the cost in the record, and a test proves it.
- The refusal text says what to do instead: ask in the reply and on the waiting page, keep working.

## Proof

Test-author writes the new cases first and shows them red on main. Cases: a live agent refuses;
a live background command refuses; none running allows; the source unreadable fails open and says
unknown. Then build until green. Run `bin/ci-job gates --base origin/main` once in the background
(90-minute timeout) before you report, and `bin/ste-changed origin/main`.

## Report

At most 25 lines: PR, head, red-run proof, gates verdict per failing or unknown step, reviewer
verdict (fresh Sonnet reviewer; the diff changes a guard).
