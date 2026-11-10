# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL3vDrEuXnStMw1crbY

## Reply at 2026-11-10T17:28:28Z UTC

IDLE (B). Lane repo-typecheck-hook (session_013NEJL3vDrEuXnStMw1crbY).
Goal: one claude-settings PostToolUse hook that runs a repo-declared typecheck from .claude/layout-extras.json key "typecheck" (owner ask ask-mw6vyc57pi part 1, 2026-11-07).
State: PR #1612, a draft at head b92e69acf on branch repo-typecheck-hook. It is unmerged, with base 174b005c1, which is far behind main, so it needs a rebase. Review round 3 PASS, net safety value zero. Handed to runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) 2026-11-07. Nothing unpushed. No agents or commands running.
Left: rebase onto main, run the batch CI (the Windows run of hooks/test_repo_typecheck.py has never run), merge. Then banchi work: add a "typecheck" entry using ["node","app/node_modules/typescript/bin/tsc",...] and drop banchi's own scripts/typecheck-hook.py entry, so tsc does not run twice.
Files: hooks/repo_typecheck.py, hooks/config_watch.py, lint/layout.py (typecheck, match_globs at file end), settings.json (config_watch PostToolUse timeout 120). Record docs/decisions/repo-typecheck-hook.md; notes in docs/debts/notes.md. Tests: hooks/test_repo_typecheck.py, lint/test_layout.py, hooks/test_config_watch_fast_exit.py.

