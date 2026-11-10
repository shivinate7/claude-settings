# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL1Aq6pKaCrB1kxda68

## Reply at 2026-11-10T17:25:53Z UTC

IDLE (B) — lane agent-name-on-spawn (session_013NEJL1Aq6pKaCrB1kxda68), repo shivinate7/claude-settings.
Goal: step agent-name-on-spawn. In a lane, a SendMessage to a named agent's bare agentId is refused, one to a nameless agent's id is asked, and a spawn with no name is refused.
PR #2122, branch agent-name-on-spawn-2, head acd9b5da4237270d249539426f326fe898e17242. Base resume-finished-reviewer (#1917). Merge after: #1917. Everything is pushed.
State: review rounds 1-3 done (FAIL haiku, PASS sonnet, PASS sonnet), net value positive, fix check PASS haiku. All posted as review records on #2122. Full hooks/test_guard.py 6087/6087; 12/12 mutants killed. Released to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za).
Files: hooks/guard_merge.py (agent_name_hit, _spawn_reads), hooks/guard.py (judge wiring, rule table), hooks/mutate_guard.py, hooks/test_guard.py (section 5k, plus named review-record fixtures), docs/decisions/agent-name-on-spawn.md.
Left:
1. Merge #2122 after #1917.
2. #1974 also edits resume_finished_hit; whichever merges second rebases onto the first.
3. Close #2078 (replaced by #2122).
4. The lane-lint glossary failure (docs/debts/notes.md:1513, "subagent") is #1917's, and its lane was told.
5. Note: unmeasured whether the PreToolUse payload keeps the Agent `name`. If not, every lane spawn is refused; the first lane spawn after install settles it.
Step resume-finished-builder duplicates #1974 (told the coordinator 2026-11-08 10:20 CST).

