# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKzJxDxuXzuwNe7fhYn

## Reply at 2026-11-10T17:23:52Z UTC

IDLE (B). Handoff for lane guard-relative-write-escape (session_013NEJKzJxDxuXzuwNe7fhYn, child of coordinator session_013NEJL2hB1pLZPDpzas7VgB).
Goal: the guard refuses an agent's relative `../` write that leaves its home (owner item 410 a), plus the guard findings routed here: sibling write forms, and quoted args as data (owner item 429 a).
State: nothing runs and nothing is unpushed. All four PRs are released to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za); none is on main yet.
- #1984 guard-relative-write-escape @ 3745935cc: round 3 PASS, net value positive. Its body is stale: it still says to wait for an owner ruling, but item 425 c (2026-11-08 10:19 CST) is applied.
- #2197 relative-write-absolute-cd @ e7f7ab9c3: Merge after #1984, batch with it. Round 3 PASS.
- #2097 guard-sibling-write-forms @ 5b7144657: round 3 PASS.
- #2234 quoted-args-unresolved @ cc3637412: Merge after #1906. A fresh chain ran: round 3 FAIL on a slug only, then a fix check PASS, net value zero. Review records are posted at each head.
Left: the merges by runner 8. Open debt kept-body-outer-keeps-all: a false alarm when a heredoc write sits beside `git add`/`mkdir`. Superseded branch guard-quoted-args-data (8e8cf9232) is unmerged; archive it to archive/guard-quoted-args-data.
Files: hooks/guard.py (`relative_write_escape`, `other_checkout_hit`), hooks/guard_core.py (`_kept_headers`, `_outer_runs_nothing_unseen`, `dir_before_segment`), hooks/guard_frozen.py (`_shell_write_hit`, `_data_words`), decision an-agent-outside-its-home-tree-must-stop, docs/debts/notes.md.
Handoff file: /root/.claude/handoffs/788c10d3-3c3c-55c6-b5bc-31af1756bcc3.md.

