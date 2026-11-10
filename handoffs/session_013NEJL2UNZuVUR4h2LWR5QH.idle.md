# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL2UNZuVUR4h2LWR5QH

## Reply at 2026-11-10T17:26:59Z UTC

IDLE (B). Handoff, lane check-line-reader (repo shivinate7/claude-settings):
Goal: step check-line-reader. A blind Sonnet check refuter reads a lane brief's Done check line against the step's title and why, and flags a check that could pass with the ask unmet. It runs when a lane brief is sent and when a step closes.
State: PR #1344 (branch check-line-reader-2, head 7bcceae99), open draft, released to runner 8, waiting for its merge. Review round 1 FAIL, fixed; round 2 PASS (reviewer sonnet). merge --lane-lint 1344 PASS. #1333 is closed (replaced by #1344).
Files: hooks/check_refuter.py (the one home: REFUTER_MODEL "sonnet", REFUTER_EFFORT None, REFUTER_TIMEOUT 45, GIT_TIMEOUT 10); hooks/call_judge.py (send_message site, rule check-refuter); hooks/shared_names.py (brief marker names); settings.json (matcher); hooks/test_check_refuter.py; docs/decisions/check-refuter.md; skills/project-ops/templates/brief.md (Done check line); GLOSSARY.md (check refuter); docs/debts/notes.md (3 low notes, refuter-*).
Rulings: owner items 284 c and 282 b (the word "refuter"), item 289 13:59 CST Nov 6 (Sonnet for all), coordinator plan of Nov 6 (step close is a second PR).
Left: the step-close PR, unblocked since #1317 merged. Triage runs one command at close; it writes a dated refuter line in the step note; skills/roadmap/build.py done_without_check only reads that line, so the build makes 0 model calls. Also: the lane-combine worktree under .claude/worktrees can be removed after #1344 merges.

