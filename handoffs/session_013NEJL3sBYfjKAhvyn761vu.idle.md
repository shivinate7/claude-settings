# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL3sBYfjKAhvyn761vu

## Reply at 2026-11-10T17:28:28Z UTC

IDLE (B). Lane notes-keep-reverify, repo shivinate7/claude-settings. No agent, command or server is running.
Goal: re-verify the 146 unverified keep notes in docs/plans/notes-sort/keep.tsv, give each keep note in docs/debts/notes.md a valid `Fix:` line in PR #1516's format, and send the new fix rows to the coordinator.
State:
- Draft PRs #1524-#1530 = branches notes-fix-lines-1..7, stacked (wave 1 based on main). Origin heads, checked 11:07 CST: 094068ef6, ebab7ac3e, 1fd5c1677, e89aaae06, b37094f6d, 0ccec261b, a64779e5b. Round-1 review done. Released to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za), to merge in wave order after #1516 (still open).
- With #1516 merged on top of wave 7, check_record_slugs passes. 247 notes still have no valid Fix (1508 at base); they belong to other lanes, or are slugless lines.
- Report branch claude/notes-keep-reverify, head a1959b187: docs/plans/notes-sort/reverify-{fix,delete,keep,prose-fix,flag}.tsv.
Left:
- The Until dates run 2026-11-14 to 2026-11-21. Any wave still unmerged on 2026-11-14 fails the Until check. Whoever holds it then must redate its Until lines (cap: 14 days out) and push the stack again.
- The flags lane's PRs #1596, #1602, #1629, #1648 and #1676 delete note lines. They must merge after #1524-#1530, because notes.md merges by union.
- Item 369 (button-merge-stale-page) is still open with triage.
Handoff file: /root/.claude/handoffs/c68f1091-de38-5d49-8a4b-567cf471024d.md (it is in this container only).

