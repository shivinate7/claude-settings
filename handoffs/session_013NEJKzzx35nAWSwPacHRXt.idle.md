# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKzzx35nAWSwPacHRXt

## Reply at 2026-11-10T17:24:53Z UTC

IDLE (B). Lane draft-pr-guard-heredoc (session_013NEJKzzx35nAWSwPacHRXt), repo shivinate7/claude-settings.
Goal: close debt heredoc-written-run-false-alarm in the one heredoc home (strip_heredoc_bodies, hooks/guard_core.py), plus the follow-ups found on the way (owner pick b, item 381).
State: all PRs are pushed, reviewed, recorded and released to runner 8 (session_013NEJL2vsmyKzJm8jUDt6za). Nothing is unpushed, and no agent or command runs.
Merge order (each `Merge after:` the one before it):
1. #1820, draft-PR heredoc guard fix: branch draft-pr-guard-heredoc-r, head b970080e8. Record: comment 6720457103.
2. #1863, heredoc-keep gap cases: branch heredoc-keep-gap-cases, head fae8e4f7b. Record: 6720625775.
3. #1897, mutant anchor check: branch lane-lint-mutant-anchors, head 9cc185927. Record: 6720627614.
4. #1915, sweep mutant anchors: branch sweep-mutant-anchor-check, head 7803cb9a4. Record: 6720780033.
5. #2304, run-dir-unclosed-tail (closes a reset after a data heredoc): head 1607f5c1c. Record: 6728455374, rounds 1-3 plus a fix check.
Left: runner 8 merges the chain. docs/debts/notes.md merges by union, so watch for retired heredoc-keep notes coming back.
Open nit: the stale label text of mutant "a runner reads no piped script" (hooks/mutate_guard.py ~285).
Files: hooks/guard_core.py, hooks/test_guard.py (heredoc-keep and heredoc-tail families), hooks/mutate_guard.py, lint/check_mutant_anchors.py, janitor/mutate_sweep.py, docs/debts/notes.md.
Handoff: /root/.claude/handoffs/1d5cd911-fc47-5ae9-b6d9-c86471cdcbac.md.

