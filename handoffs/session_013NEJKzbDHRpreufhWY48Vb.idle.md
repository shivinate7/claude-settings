# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKzbDHRpreufhWY48Vb

## Reply at 2026-11-10T17:24:14Z UTC

IDLE (B). Lane one-home-check, handoff:
- Goal: build the plan of PR #1106 to check rule `building-one-home-per-capability` (one home per capability), with owner answers 337-341 (Nov 7 12:34 CST), plus the coordinator's follow-ups.
- State: nothing running, nothing unpushed. Every PR has a review record for its head and was handed to batch runner 8. Merge state last read 2026-11-08.
- PRs, in merge order, with heads:
  - #1432, the one-home check: db63e3c27
  - #1903, stale_cites lists the tree once (after #1432): d81a8f6f6
  - #1562, note fixes: 964d4c80b
  - #1927, docs-only dedupe of the debt notes (after #1562): 3f25ba000
  - #1564, one shared code-block pattern: 853dce6b6
  - #1643, one shared code-block walker: 379eb58d4
  - #1563, held-out measure of the paraphrase pass: d2a94ccec, any time after #1432
- Left: runner 8's merges. A head moved by a later main merge needs a new fix check and record.
- Triage, already sent to the coordinator:
  - the union merge in notes.md brings back deleted lines
  - a test-author-scope refusal of a whole CI test step, a possible false alarm
  - 9 duplicate ids in notes.md on main
- Files: docs/decisions/one-home-check.md, lint/word_runs.py, lint/find_copies.py, lint/stale_cites.py, actions/ste-lint/run.sh, docs/debts/notes.md.
- Handoff file: ~/.claude/handoffs/3f1ebe84-5078-5cf6-9902-f0d452c0dc90.md

