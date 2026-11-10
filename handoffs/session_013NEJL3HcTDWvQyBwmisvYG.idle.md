# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL3HcTDWvQyBwmisvYG

## Reply at 2026-11-10T17:27:43Z UTC

IDLE (B)
Goal: owner item 279, pick a. A reviewer's brief holds the task, the diff or a pointer, and the rulings. It never holds a builder report or a prior verdict. hooks/guard.py rule reviewer-brief-blind refuses a reviewer or refuter spawn that breaks this.
PR: #1366, draft, branch reviewer-brief-blind-build, head efb927a0b, unmerged, all pushed.
State: 3 review rounds done. Round 3 PASS, net safety value positive. Lane lint PASS, fix check PASS (2026-11-08 04:10 CST). Handed to runner 8 to merge.
- It must batch after lane blind-plan-refuter (#1336). The branch merges that lane's branch for REFUTER_ROLE in hooks/guard_core.py.
- Lane #1376 (session_013NEJL1BCgLVUACYU5ujv9A) is stacked on this head.
Files: hooks/guard.py, hooks/mutate_guard.py, hooks/test_guard.py, hooks/test_agent_brief.py, CLAUDE.md (rule roles-resume-by-name), agents/reviewer.md, lint/rule_mechanisms.json, docs/decisions/reviewer-brief-blind.md, docs/debts/verdict-instruction-false-alarm.md, docs/debts/notes.md.
Left:
1. The merge, by runner 8.
2. Fix lane verdict-instruction-false-alarm. The debt: a brief line "End your report with a verdict: PASS, FAIL or PARTIAL." is refused. The coordinator says a lane was measuring it.
3. Owner item 299 is open (a, b or c; b is built). If the owner picks c, lane reviewer-brief-template starts: a reviewer brief template, a CLAUDE.md clause, and a remedy that points to it.
4. Three notes in docs/debts/notes.md: verdict-bold-after-colon, verdict-other-phrasings, verdict-regex-slow-line.

