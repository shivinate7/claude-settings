# Handoff: lane guard-false-alarm-cull (written 2026-11-19 00:30 CST)

Slug: guard-false-alarm-cull. Role: lane (decision session-tiers). Parent: coordinator (session_013NEJL1gw6EdrSyvHkTUEx6). Started 2026-11-12 11:19 CST. No pull request is open from me except the twelve below, all drafts; I marked none ready and merged none.

## Goal
One cull fixes or deletes each guard or check with a recorded wrong refusal, whichever costs less; after it, wrong refusals are notes only. Source: coordinator brief 11:19 CST Nov 12; grant owner R5 (2026-11-10 15:04 CST, "option e works for now", and 15:18 CST); step guard-false-alarm-cull; decision cull-guard-wrong-refusals.

## Branches and PRs (heads read from GitHub 2026-11-19 00:29 CST)
Merge order sent to runner 10 (session_013NEJL2f1YCYsvLdpFqtWP3) on 2026-11-12 21:00 CST. Each PR passed `merge --lane-lint` on the head named (the lint was run before this table; heads unchanged since).

| Order | PR | Branch | Head | State now | Family |
|---|---|---|---|---|---|
| 1 | 3028 | cull-report-guard | 601424fea2f159b551b7bf7f4a75df4b0fe0e417 | open, draft | 1 report guard: Recovered/Handoff-gave check deleted; prompt gets a `Handoff gave count` line |
| 2 | 3029 | cull-question-form | a516a55fd306b87adc3be9c0c6802b2b249212de | open, draft | 2 Departs-from dash check deleted |
| 3 | 3030 | cull-test-temp-run | 6ea9e087568e53c69858fd36b0eb02b881fbfc64 | open, draft | 8b test temp-run guard reads 3.9 code |
| 4 | 3043 | cull-debt-retire-note | a2f593dfc82e67c1189b75a79743fedfad8baabb | open, draft | debt check: a wrong refusal closes by a notes line |
| 5 | 3031 | cull-ruling-kind-home | dba9fe0879b367e4d343cf7be8ec9c21c07e6ad6 | open, draft | 7 |
| 6 | 3033 | cull-merge-confirm-head | 83c758e965eaf7573b9285b25be58e1054e4812f | CLOSED (not merged) | 9 |
| 7 | 3032 | cull-text-reads | 0d6f7bfa76d41c1e3dae37561b40e45e5c8dfcdd | open, draft; stacked on 3033's head | 8 |
| 8 | 3034 | cull-shared-tree | d509685230dfebab6ee99baf2515f867bc380369 | CLOSED (not merged) | 5 |
| 9 | 3035 | cull-glossary-decision-id | 99b05dd429b65d10312cc038a920893b615e14bf | open, draft | 10 |
| 10 | 3036 | cull-narration-hex-id | 9853d78517eee073bcdc3a9cfface2978491cac7 | CLOSED (not merged) | 11 |
| 11 | 3037 | cull-frozen-reads | 21ad144f8f7ad75a81a234b36cd654daae9d7b2e | open, draft | 4 |
| last | 3056 | cull-docs-notes | 37675a604e3ab53db0e53f5e36a60793ac569783 | open, draft | docs (notes, stale records) |

I did not close 3033, 3034 or 3036; someone else did. I do not know why. Check before reusing: 3032 contains 3033's commits, so 3032 cannot merge alone without them.
Note-only branch: cull-feedback-guard (family 3), archived at archive/cull-feedback-guard 7315d46d5. Family 6 not built.

## Review records (per branch: round, reviewer model, verdict)
- 3028 round 3 PASS, sonnet, net value positive (narrow). 3029 round 3 PASS, sonnet, positive. 3030 restart round 1 PASS, haiku. 3031 round 1 PASS, haiku. 3032 round 2 PASS. 3033 round 2 PASS. 3034 round 3 PASS, sonnet, positive (closed 3 holes, opened 1). 3035 round 1 PASS, haiku. 3036 round 3 PASS, sonnet, positive (small). 3037 fix check PASS, sonnet.
- 3043 (a check change): round 1 FAIL haiku, round 2 FAIL sonnet, round 3 sonnet net value zero; two wording fixes and one test gap filed as notes.
- 3056: round 1 FAIL haiku, round 2 FAIL sonnet, round 3 PASS sonnet (no net-value test: no guard or check changed).
- After the reviews, comment-only or rename fixes landed on 3028, 3029, 3031, 3032, 3034, 3043 (dated or hash comments, a glossary name); each re-linted green.

## Done
Every family above built with a test-author's red cases first. Triage rulings 18:55 CST Nov 12 applied: the debt check changed (3043); handoff-loss count kept as a `Handoff gave count` line in the handoff file, written by the prompt on 3028 and read by triage on demand.

## Unfinished
- No branch is merged to main; runner 10 owned the merges. Whether it merged any, I do not know; the table above is the state I read.
- 3056 has one expected red (lint/test_report_guard_remedy.py test_3) until 3028 merges, and its six debt deletions need 3043 merged first. Expect a hand merge of docs/debts/notes.md with 3028 (about lines 1107 and 1410: take 3028's "three reasons" text).
- Branch cull-narration-hex-id and sibling cull-narration-hex-id-fix (not mine) edit the same docs/debts/comment-narration-limits.md; the coordinator picks which merges.
- Records worded for the post-3028 state: docs/decisions/precompact-handoff.md line 42 and skills/project-ops/templates/operating-model.md line 42 (rewrite in place after 3028 merges). docs/plans/restart-plan.md about line 645 is stale after 3028.
- Conflict between 3028 and 3029 at lint/test_report_guard.py 2131-2135: keep the re-pointed row.
- Pace numbers and the sweep offer are owed at the last merge: `python3 ~/.claude/janitor/sweep.py --root <repo> --attended --fast`, preview first.

## Next step
When runner 10 merges 3028 and 3043, run a merge-main fix lane on 3056 (plain merge, never rebase), then re-lint 3056.

## Refused acts and nuisances (all reported; none routed round)
Spawn guard refuses a sonnet model for review round 1 (round 1 runs haiku). Hand-made-worktree guard refused agents' `git worktree add` (red-run checkouts). `verdict` is not on agents' PATH. Concurrent `merge --lane-lint` runs collide on `git fetch` (run one at a time). Pointer-checkout guard refused a branch switch in the main checkout. A scratchpad commit-message `-F` file was refused (scratchpad-commit-msg-owner). Probe guards fired on quoted text in read-only probes. Hooks refused: a pipe out of verdict, a detached launch, printing process arguments.

## Owner rulings and relayed picks I hold
R5 (2026-11-10 15:04 and 15:18 CST); owner item 630 pick b (accept the three narration limits, add pins); owner item 109 pick b (a way to see handoff losses; via triage); coordinator 13:32 (family 8b restart, 3.9-safe), 14:02 and 14:49 (family 4 one fix lane; family 11 pick b), 15:29 (family 3 add-on, no fifth restart), 16:43 (family 3 note only; hand each passing family to runner 10), 18:37 CST Nov 12 (open a draft PR per branch; docs merges main in, never rebases; fresh round 1 on the merged docs head); triage 18:55 CST Nov 12 (items 669 and 670 withdrawn: wrong refusals become notes, debt check brought in line; keep a handoff-loss count somewhere read on demand); coordinator 2026-11-19 00:26 CST (this handoff and wind-down). All have a home in the records on the branches above, or in the coordinator's table.

## Agents
None running. Roles used, each one role: test-author, builder (sonnet; opus on family 4 round 3), reviewer (haiku round 1, sonnet rounds 2-3), record-writer. Their worktrees are under `.claude/worktrees/agent-*` in the main checkout; many are left over (red-run checkouts and finished agents); the sweep offer above removes them.

## Files and commands
Decision: docs/decisions/cull-guard-wrong-refusals.md. Notes: docs/debts/notes.md. Step record: roadmap/data/steps/guard-false-alarm-cull.json on origin/roadmap. Session handoff: /root/.claude/handoffs/98bccdf5-19bc-5887-b976-35c0d8e6d38b.md (not committed). Lane lint: `/root/.claude/bin/verdict /root/.claude/bin/merge --lane-lint <pr>`. Red-run check: `lint/check_red_run.py --base origin/main`.
