# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKzUUyEjaYnf5oBR6Wp

## Reply at 2026-11-10T17:23:40Z UTC

IDLE (B)
Goal: one definition of "the machine is loaded", shared by the guard's load brake and sim-lease. Owner items 304 a (one definition) and 309 a (memory and disk only; sim-lease drops its load-average bars). Coordinator 15:31 CST 2026-11-06: an unread reading holds a sim-lease grant (item 276 a).
Repo shivinate7/claude-settings, branch lane/one-load-definition, draft PR #1369, head 5055360d8, base main 380a24b5 (now far behind main).
State: built and tested. Test-author red first, then green: hooks/test_guard_load.py, lint/test_sim_lease.py, lint/test_sim_test.sh, hooks/test_install_src.sh, load-brake family 258/258. Round-1 review PASS (reviewer haiku), wording findings fixed. Handed to runner 8 on 2026-11-06 16:45 CST, never merged. Nothing unpushed.
Files: new hooks/guard_load.py (read_load, load_verdict, limits); hooks/guard.py (brake calls guard_load, adds guard_load to _FAMILY_MODULES); bin/sim-lease (no sysctl or loadavg); hooks/load_rows_test.py and lint/guard_load_fake_test.py (shared test rows and stand-in); decision one-load-definition (new); decisions machine-load-brake and sim-lease-tool and skills/ios-apps/SKILL.md (rewritten); docs/debts/notes.md (one note).
Left: update the branch onto current main, resolving conflicts in guard.py, sim-lease, the tests and the records, and rerun those suites. Then mark the PR ready, batch it and merge. On merge, triage closes item 309. Plan align-watchers Q6 (PR #1349) should read "decided (a)".

