# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL3XjWoVXFLZP2Lfwy4

## Reply at 2026-11-10T17:27:56Z UTC

IDLE (B). Handoff for lane mcp-merge-unguarded:
Goal: settings.json's guard.py matcher had dropped the GitHub MCP tools the guard judges (commit 97ffeb3f), so the MCP merge skipped merge-checks and the MCP create skipped draft-pr. Put both tools back in that matcher.
PR #1314 (route the GitHub MCP merge and create tools to the guard), branch mcp-merge-unguarded, head 7a46a0b94, open draft. It was handed to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) and waits only for its merge. It batches alone, as a guard change.
State:
- Lane lint PASS at 7a46a0b94.
- The review record is posted on the PR: round 1 FAIL (reviewer haiku), round 2 PASS (reviewer sonnet), net value positive.
- Nothing is unpushed.
Files: settings.json and docs/catalog.md (the matcher), lint/test_settings_matcher.py (the test: it parses guard.py and every guard module it imports, at any depth, and checks that each mcp__ tool name they contain is in the real matcher), docs/debts/notes.md (notes bare-merge-skips-host-merge-tool and bare-merge-reads-folder-not-repo).
Left:
- Merge #1314.
- Open debt: merge_check reads the caller's folder (has_workflows, pinned_required, the ignore list), not the named repo, for a cross-repo merge.
- Notes: hooks/decision_watch.py keeps a second MERGE_TOOLS copy. The other-checkout guard refused a read-only cd, a possible false alarm.
- Push 754496e3 (an earlier merge of main into the branch): the pusher is unknown.
Handoff file: ~/.claude/handoffs/session_013NEJL3XjWoVXFLZP2Lfwy4.md

