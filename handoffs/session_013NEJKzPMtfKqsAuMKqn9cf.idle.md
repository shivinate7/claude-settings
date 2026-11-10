# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKzPMtfKqsAuMKqn9cf

## Reply at 2026-11-10T17:23:43Z UTC

IDLE (B). Lane notes-name-their-fix, handoff:
Goal: each notes line or debt file a branch adds names its fix (owner, 2026-11-07 13:20 CST, "why not fix it then"; 13:25 CST, "I want the guard itself").
PR: draft #1516, repo shivinate7/claude-settings, branch notes-name-their-fix, head b2410e60b (merged with main 422cbbdfe). It is with batch runner 8, to batch alone because it changes a guard. It has not merged.
State: review round 1 FAIL, then fixed. Round 2 PASS with notes. Fix check and lane lint PASS on b2410e60b.
Built:
- lint/check_record_slugs.py, the one home of the Fix grammar. Forms: step:<slug> on origin/roadmap; none — owner decides / needs the Mac / needs a Windows run / rare and harmless, with Until: within UNTIL_CAP_DAYS=14 (page item 360 b); already fixed on main <sha>, which must be an ancestor of origin/main.
- A ratchet: the count of notes with no valid Fix may not rise above the merge base's count.
- lint/report_guard.py: the Stop check on this turn's commits, by author time.
- skills/roadmap/build.py: the upkeep list prints one line per expired note.
Records: decision notes-name-their-fix (new); the owner ruling in decision cull-rules; docs/debts/README.md; the docs/debts/notes.md header plus 3 note lines, each with Until 2026-11-21.
Left: runner 8 merges it, after a fresh merge with main if main has moved. Waiting on it: #1524 to #1530, #1619, #2088, lanes notes-keep-reverify and notes-sightings-expiry.
Known notes, not fixed: misses fail open on a wake or clock lag; a cherry-pick made this turn is not judged; MCP remote writes are out of scope.

