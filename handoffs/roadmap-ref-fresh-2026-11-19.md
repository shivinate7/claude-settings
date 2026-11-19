# Handoff: lane roadmap-ref-fresh (2026-11-19 00:30 CST)

## Slug, branch, head

- Slug: roadmap-ref-fresh. Step: roadmap-ref-fresh-before-verdict (ledger row roadmap-ref-fresh). Grant R67 (owner 10:50 CST Nov 13, express).
- Branch: roadmap-ref-fresh. Head: d149374d1eb004a6d122091a47e6c66d82ba8370 (merge of main 1ae9d2b0fc into 3388bf6ebe79).

## Open PRs

- PR 3253, draft, never marked ready. Head d149374d1e. Lane lint PASS at this head (comment 6885049862). Review record at this head: comment 6884742419 (round 1 haiku FAIL, round 2 sonnet FAIL, round 3 sonnet PASS, Fix check on 3388bf6ebe sonnet PASS, net value positive). REST read 2026-11-19 00:26 CST: state open, mergeable_state dirty (main has moved past 1ae9d2b0fc since the merge).

## Done

- Shared helper lint/roadmap_ref.py (`fresh_ref`): fetch origin roadmap, bounded 2 s, own process group, "read as of <time>" on failure; fresh only if FETCH_HEAD roadmap line is under 60 s old and its sha equals the origin/roadmap tip (ref file or packed-refs, no git process).
- Six readers wired: lint/ruled_store.py, hooks/feedback_guard.py (repeats read), hooks/sendmessage_state.py (RULINGS_TIMEOUT 5 s to 3 s), hooks/override.py, hooks/question_form.py, hooks/session_start.sh.
- Tests: new lint/test_roadmap_ref.py, hooks/test_roadmap_readers.py; fixtures primed in the cost, feedback, call_judge, report_guard, sendmessage, session_start and question_form suites.
- Records rewritten in place: owner-feedback-inbox, ruled-store-one-home, agent-model-cap, question-form, haiku-prompt-hooks. Debts: roadmap-refetch-no-branch, roadmap-fetch-remote-hang, roadmap-fetch-other-readers (ten readers), roadmap-fetch-windows-orphan; notes in docs/debts/notes.md.
- Handed in to runner 10 (session_013NEJL2f1YCYsvLdpFqtWP3) and coordinator (session_013NEJL1gw6EdrSyvHkTUEx6) 2026-11-14 16:17 CST. Time and CI cost sent to triage (session_013NEJKzCzoWhfP8FMCPtQU6).

## Unfinished

- PR 3253 not merged. Main has moved since d149374d1e; the PR reads dirty.
- Follow-up notes PR (unstarted, waits for merge): feedback_guard.py `note or (...)` skips the second root's freshness check; page remedy says "record branch" but the helper fetches only `roadmap`; cold first roadmap fetch may exceed 2 s; `_restore` can drop a concurrent fetch's lines; a guard for `case_` functions missing from `CASES`; stop_hook_active emit site untested; docs/debts/roadmap-fetch-remote-hang.md line 4 cites line numbers by position.

## Next step

1. Merge the newest main into roadmap-ref-fresh (ordinary merge, edit conflicted paths only; past conflicts were in .github/scripts/ci-scope.sh: keep main's `shoot` line and add `lint/roadmap_ref.py|` after `lint/ruled_store.py|`). A clean merge keeps record 6884742419. A conflicted merge needs one fresh sonnet fix verifier, then one record: `--round 1:reviewer:haiku:FAIL --round 2:reviewer:sonnet:FAIL --round 3:reviewer:sonnet:PASS --net-value positive --fix-check <previous head>:reviewer:sonnet:PASS`, posted as printed.
2. `~/.claude/bin/verdict python3 merge/merge.py --lane-lint 3253` (background, time limit 3900000 ms); hand in again to runner 10.

## Refused acts

- Record tool refused: a lone round 2; a fix check with no earlier log at that head. The coordinator replaced its own commands after each refusal (13:04 and 13:12 CST Nov 14).
- Guards refused: worktree add in the shared checkout for test-authors, `git -C` with runtime paths, a push to a branch named roadmap, deleting leftover worktree .claude/worktrees/agent-a17e2b8d7dc92a400-red (waits for the janitor sweep).

## Owner rulings held

- Grant R67 (owner 10:50 CST Nov 13): express, tracking. Source: coordinator relay 12:42 CST Nov 13.
- Coordinator rulings: 09:10 CST Nov 14 (merge main first, fresh review at the final head), 09:51 CST Nov 14 (filing and export reads stay as debts), 13:04 and 13:12 CST Nov 14 (record route; the 13:12 route used). All coordinator-relayed, none owner-typed.

## Agents (all finished, none running)

Worktrees live under /home/user/claude-settings/.claude/worktrees/ and are branches worktree-agent-<id>; all pushed to roadmap-ref-fresh by merge.
- test-authors (haiku): ae640c80f717286b4, aa668f0d2d293d27c, a04409cd072eaff2c, adc6a2985e1b50ddd, a4ecdad79ae83e3a2 (merge, blocked on a guard).
- builders (sonnet): a6d3db9903477df64, a1e1b1fef26efabed, a0f2b52550c7a226a, a4c606183abe0d0d6.
- record-writers (haiku): aee0f98e32e994350, a2eb65a4954cdf601.
- reviewers: round 1 haiku a12f5d795fee73872, aa86394b48ad3dede; round 2 sonnet ac649533cf559925c; round 3 sonnet a3fc2a31423787ff4; fix verifiers sonnet adac15effe148da25, a2dd7279a1c0f042a; one round-2 reviewer stopped by me a034be006cf024c32.
- Explore (sonnet, audit): aa194996e95dc5e0d.
