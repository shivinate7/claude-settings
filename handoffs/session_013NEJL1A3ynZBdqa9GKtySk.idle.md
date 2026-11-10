# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL1A3ynZBdqa9GKtySk

## Reply at 2026-11-10T17:25:34Z UTC

IDLE (B)
Goal: roadmap step argv-dump-guard (order 945): a guard that refuses commands printing other processes' full arguments (ps aux/-ef/-o args, pgrep -a/-l -f, /proc/*/cmdline reads, pstree -a, top -c, PowerShell CommandLine), after the 2026-11-09 19:59 CST Tailscale key leak.
State: repo shivinate7/claude-settings, branch argv-dump-guard, PR #2490 (open draft), head 731fee596ca86e9b970d5508c91ce87734ab2220, fully pushed. Rounds 1 to 3 done (round 3 net value positive), review record posted on the PR (comment 6761388423), lane lint PASS on this head. Released to runner 8 for batch 72 at 01:28 CST; not merged as of 11:26 CST.
Left: GitHub now reports the PR as mergeable_state "dirty" (main moved past 0e6509a96), so the runner or a new lane must merge main in (ordinary merge; hooks/guard.py wiring at step 5c and hooks/test_guard.py are the likely conflict sites) before it can join a batch. The PR body is stale (says rounds are owed). Open gaps are in docs/decisions/process-args-guard.md "Not read" and docs/debts/notes.md (3 notes).
Files: hooks/guard_argv.py (new), hooks/guard.py, hooks/guard_kill.py (remedy now `pgrep -f playwright`), hooks/mutate_guard.py and hooks/test_mutate_ci.py (table row and entry), hooks/test_guard.py (argv: cases, playwright_remedy_case re-pointed), docs/decisions/process-args-guard.md (new), docs/decisions/playwright-browsers-path.md, docs/debts/notes.md.

