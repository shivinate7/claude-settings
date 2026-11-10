# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKzXmA85KHJfwprwzBb

## Reply at 2026-11-10T17:23:43Z UTC

IDLE (B)
Goal: roadmap step repo-protected-paths (owner ask ask-mw6vyc57pi part 2): guard rule protected-path. A repo lists "protected-paths": [{"path","why"}] in .claude/layout-extras.json; the guard refuses Write-family, shell and python/node writes under those paths. This keeps the deny working in project cloud threads, where a repo's own settings do not load.
State: PR #1661 (draft, open, unmerged), branch repo-protected-paths, head 531314cbb, base main 174b005c1. Review: 3 rounds; round 3 (reviewer sonnet) PASS, net safety value positive. Handed to runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) 2026-11-07 17:44 CST. Nothing unpushed.
Left:
- Batch and merge #1661. Main has moved about 2,785 commits since base 174b005c1, so expect a rebase; conflicts likely in hooks/guard.py, hooks/guard_frozen.py, hooks/guard_core.py and lint/layout.py (lane repo-typecheck-hook also edits layout.py).
- Mutation tests do not run hooks/test_guard_protected.py; filed as a note with "Fix: step:mutate-guard-split".
Files: lint/layout.py (protected_paths after artifacts()), hooks/guard_frozen.py (is_protected, protected_shell_hit, _protected_write), hooks/guard.py (rules 7a and 7d, PROTECTED_WRITE_HINT), hooks/guard_core.py, hooks/test_guard_protected.py, lint/test_layout.py, docs/decisions/protected-path.md, docs/debts/notes.md.
Rulings: restore/checkout of a listed path is a write (coordinator pick 2026-11-07, in protected-path.md).

