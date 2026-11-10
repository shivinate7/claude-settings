# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKzKA8bkAW7ossmC85D

## Reply at 2026-11-10T17:23:33Z UTC

IDLE (B) — lane item-cite-carries-name.
Goal: rule speak-cite-id-plus-gloss gets a check that a page item number carries its short name, in replies and in the session handoff. Incident: owner ask ask-mw79tmz6x2, a handoff that cited items by number only.
State: built and reviewed (round 1 FAIL, round 2 PASS, net value positive). PR #1790 (item cites carry their short name) is an open draft on branch lane-item-cite-build, head 1a13ab443, base main. It was handed to batch runner session_013NEJL2vsmyKzJm8jUDt6za on Nov 7 and is not merged. Nothing is unpushed.
Files: lint/report_guard.py (`bare_item_cite`, `bare_cite`, `gloss_lead`); hooks/guard.py (`handoff_cite_hit`, `_lint_module`); tests in lint/test_report_guard.py class ItemCiteTests and in the hooks/test_guard.py family handoff-cite; docs/debts/item-cite-plural-tail.md; docs/debts/notes.md (5 lines).
Scope ruling: coordinator option b, 22:45 CST Nov 7. Handoffs: every "item N". Replies: page or waiting-page item cites, and a bare "item N" only when the reply names the page or triage. The ruling's home is the PR body and the notes line.
Left:
- `merge --lane-lint 1790` never ran (worktree isolation refused it). `ci-job --lint` plus `ste-changed` passed instead.
- Main has moved about 2,800 commits since base 394ad4863, so the branch likely needs a rebase or conflict fix in report_guard.py and guard.py before it joins a batch.
- Then integration CI, then merge.
Gap for triage: lane-lint-in-isolated-worktree (`merge --lane-lint` cannot run in a worktree-isolated lane session).

## Reply at 2026-11-10T17:23:37Z UTC

Correction to my IDLE (B) handoff for lane item-cite-carries-name. "About 2,800 commits" is unmeasured. It was the local main checkout's lag, not this branch's. How far branch lane-item-cite-build (head 1a13ab443) is behind main is unknown, so a rebase may or may not be needed.

