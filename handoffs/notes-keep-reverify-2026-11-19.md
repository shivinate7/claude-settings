# Handoff: lane notes-keep-reverify, 2026-11-19

## Who

- Lane: notes-keep-reverify (step `notes-keep-reverify`, then judge-flags-batch101 and judge-flags-batch102).
- Repo: shivinate7/claude-settings. Session: session_013NEJKzimwz9GDpxMtjZrqi.
- Parent: coordinator session_013NEJL1gw6EdrSyvHkTUEx6. Batch runner: session_013NEJL2f1YCYsvLdpFqtWP3 (runner 10). Triage: session_013NEJKzCzoWhfP8FMCPtQU6.
- Handoff branch: `archive/handoff-notes-keep-reverify`. Nothing else is open.

## Pull requests (REST state, read 2026-11-19 00:30 CST)

All merged by the batch runner. No PR of this lane is open.

| PR | Branch | Head | State |
| --- | --- | --- | --- |
| 2623 | notes-fix-w1 | f075a9e3e4 | merged (prose batch 95) |
| 2624 | notes-fix-w2 | ec6c1f33e9 | merged |
| 2625 | notes-fix-w3 | a62c520502 | merged |
| 2626 | notes-fix-w4 | 32b3d696a6 | merged |
| 2627 | notes-fix-w5 | 60e8793812 | merged |
| 2628 | notes-fix-w6 | c7dbdd4d67 | merged |
| 2629 | notes-fix-w7 | b58d92a5be | merged |
| 2648 | notes-fix-w8 | a320a730c5 | merged |
| 2649 | notes-four-gaps | 339c36175b | merged |
| 2743 | notes-dedup | ae29205aa9 | merged |

Closed as replaced (branches kept): old PRs 1524 to 1530 (notes-fix-lines-1 to 7).
Not mine: PR 2757 (record-gloss-link-checks, draft, open) builds the records gloss and Decision-link check.

## Done

- Waves 1 to 7: Fix lines for about 1,200 kept notes in `docs/debts/notes.md`, rebuilt from main (PRs 2623 to 2629). Wave 7 first restored 5 notes the old wave had deleted that were not on the proven-delete list.
- Wave 8 (2648): 21 notes that waves 1 to 7 skipped.
- Four gaps (2649): 3 debt records (comment-narration-limits, merge-remedy-hits-role-refusal, other-clone-unread-writers); note scratchpad-shared-per-session got `Fix: step:scratch-rm-other-agent`.
- Dedup (2743): 252 duplicate note rows removed (union-merge leftovers); judge-flags-batch101 (10 lines) and judge-flags-batch102 (59 added lines checked by hand) backed or cut.
- Cause of the duplicates: the notes file merges by union, so two PRs that touched the same row kept both forms.

## Unfinished (nothing started)

1. Follow-up PR, one file `docs/debts/notes.md`, built from current main (bd0759f83c at 2026-11-19):
   - 21 keys that still have two rows with differing text: keep the newer row per key from git history, list each pick. Keys from the dedup writer's report: stall-message-delivery-unproven, write-refusal-keeps-old-out, roadmap-update-republishes-live-code, batch-check-reads-designdata-only, cloud-mirror-sha-write-fails, waiting-page-chat-first-heading, lane-force-push-refused, reviewer-no-session-tools-general-purpose-spawn, handoff-unread, mistake-check-plain-fault-words, cannot-claim-reason-verb-missing-forms, ci-secondary-limit-unmeasured, sweep-fetch-fail-wrong-cause, builders-own-test-commit-forgotten, grant-no-word-miss, cannot-claim-open-adjective-reads-as-act, rm-shim-bypass-forms, rm-shim-glob-passes, command-in-item-str-replace, ps1-copy-skill-prune-no-backup; opus-plain-ask sits on 7 rows. On main today 56 keys still have more than one row: recount first.
   - Two closes: note `pointer-edit-comment-overclaims` (premise already fixed) and the unbacked "(PR 2638 decision: guard-guards-mistakes-only)" parenthetical if any row still carries it.
   - Fix lines for the owner's 6 notes, from the picks on the waiting page:
     - merge-by-button-stale-page: `Fix: step:auto-merge-refused` (owner item 369 a; step ready).
     - cites-lack-gloss-unchecked and debt-decision-link-unchecked: `Fix: step:records-gloss-link-sweep` (owner item 365 b; step doing; draft PR 2757 builds the check). On main today both rows have no Fix line.
     - guard-heredoc-os-system: `Fix: none`, owner decides (owner item 366 b: keep the gap). Main already reads "Fix: none — owner decides".
     - install-skill-fail-exits-0: delete the note; step install-skill-fail-exit is done (owner item 368 a). Main already points it at that step.
     - one-term-per-meaning-unchecked: `Fix: step:one-term-warn-lint` (owner item 533 a, coordinator 12:04 and 12:07 CST Nov 12; code step, built by another lane; do not build the lint). Main reads "Fix: none — owner decides" today.
   - Check first: the notes folder rule changed ("the old notes file takes deletes only"), so confirm whether notes.md still takes edits before writing.
2. Notes `ps-quote-forms-unread` and `walk-curly-quotes-plain` stay open as needs-windows (a Windows run decides). Triage knows.
3. The merge judge has not re-run on the 2743 lines.
4. Until dates on the wave notes ran 2026-11-19 to 2026-11-26; the 14-day cap check (PR 1516) was not on main when written. Expiry starts today: recheck what the date check does on main.

## Next step for whoever picks this up

Read main's `docs/debts/notes.md` (recount duplicate keys, read the six rows), then brief one record-writer on a new branch from main with the list above. Lane lint, docs-only review record, hand to the batch runner.

## Refused acts

- A move of the shared checkout off main was refused by the pointer-head guard; I used a worktree (remedy followed).
- A quiet `git fetch -q` was refused by the silent-write guard; reran without the flag.
- The record-writer guard refused a `.py` script write by the dedup writer (even in scratchpad); the logic ran inline. Possible false alarm: the brief asked for a scratchpad script.
- No refusal was routed around.

## Owner rulings I hold (homes)

- Page items 365 b, 366 b, 368 a, 369 a, 533 a: homes are the waiting page items and the steps named above. Items 528 to 532 were closed by triage as covered by those.
- Coordinator picks (process-only): the four-gap split (2026-11-12 04:21 CST), all 273 duplicates in one PR (08:07 CST), plan for the 21 pairs (08:42 CST).

## Agents (all finished; names resume from transcript)

- notes-w1 to notes-w8, notes-ruled12, notes-four-gaps, notes-dedup, notes-flags101, notes-flags102: record-writer, haiku, each in its own worktree under `.claude/worktrees/agent-*`. Branches: notes-fix-w1 to w8, notes-four-gaps, notes-dedup. None is running.

## Reports owed

None. Last report to the coordinator: 2026-11-12 (dedup PR handed to runner 10).
