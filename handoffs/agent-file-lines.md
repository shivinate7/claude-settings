# Lane handoff: agent-file-lines

Written by the lane session at wind-down, 2026-11-08, for its coordinator. This file is a snapshot: read the live PR first.

## State

- PR #1114, branch lane/agent-file-lines, head 1efc06f3. Merged.
- Review: 3 rounds. Round 3 PASS (reviewer sonnet), net safety value positive. The install fix after the batch drop: PASS (reviewer haiku).
- Source: audit rows staged-diff-step-agents and taskstop-all-agents (docs/plans/deep-audit/report.md on branch audit/deep-1102).

## Built

- hooks/agent_brief.py: one COMMON line carries the staged-diff step to each agent type that commits. The copies in agents/builder.md and agents/test-author.md are gone.
- agents/design-reviewer.md and agents/claude-code-guide.md: the TaskStop line. claude-code-guide lists TaskStop in its tools.
- hooks/test_agent_brief.py, lint/test_check_agent_models.py: each agent file is checked for the step and the line. hooks/tool_lists_test.py holds the one tool-list reader.

## Open

- Notes tool-list-comment-only-key and can-write-partial-deny in docs/debts/notes.md.
