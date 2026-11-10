# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL3NAnujQ8Pbt5dXkwP

## Reply at 2026-11-10T17:28:00Z UTC

IDLE (B)
Goal: roadmap step merge-batch-split-and-pipeline. The merge tool splits a red batch and builds the next batch on a running one. A follow-up lane, batch-red-fixes, fixes that PR's 8 notes and debt drop-red-hits-every-suite.
State: no agent, command or worktree of mine is running. Nothing is unpushed.
PRs (open drafts, clean against their stacked bases, review records posted, net value positive, handed to batch runner 8 session_013NEJL2vsmyKzJm8jUDt6za):
- #1894, branch merge-batch-split-and-pipeline, head 2e03010056fe3730d91427da870d9cec44bd2a4f, base merge-builds-batches-2 (#1815). Merges after #1815.
- #2027, branch batch-red-fixes, head 504cfd75f991c7258990e1404c05f3be553a2654, base merge-batch-split-and-pipeline. Merges after #1894.
What it adds: merge --build-batch --drop-red <PR> (drop the red lanes and their dependents, rebuild by merges, post Batch: red lines; the merge tool refuses those heads); --on <branch>; a lint fail re-runs once; red acts age on the lane round limit.
Left: batch and merge #1815, then #1894, then #2027. Main has moved about 2785 commits since 7e5528c43, so expect a rebase or merge-from-main and a fresh lane lint before batching. Three notes in docs/debts/notes.md (batch-red-marked-ledger-untested, batch-red-unmarked-int-line, batch-red-test-msg-batch-head) carry Fix: none until 2026-11-21.
Files: merge/merge.py, merge/test_merge.py, README.md, docs/debts/notes.md.
Ruling home: orchestrator pick 05:58 CST Nov 8 (a lane's Batch: red line binds its exact head; an integration line binds every head holding it), stated in the #2027 body.

