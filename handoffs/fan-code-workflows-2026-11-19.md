# Handoff: lane fan-code-workflows, 2026-11-19 00:3x CST

Slug: fan-code-workflows. Session session_013NEJL11UY3p6jnSXrTspmu. Parent coordinator session_013NEJL1gw6EdrSyvHkTUEx6; batch runner 10 session_013NEJL2f1YCYsvLdpFqtWP3; triage session_013NEJKzCzoWhfP8FMCPtQU6. Written on the coordinator's wind-down order of 00:26 CST Nov 19 (owner order 00:19 CST). Checkout /home/user/claude-settings on `stable`; this file lives on branch archive/handoff-fan-code-workflows (from origin/main bd0759f83c).

Goal: get five PRs merged, each with lane lint PASS and a review record at its live head, handed to runner 10. Source: owner grant 13:51 CST Nov 11 (restart-plan R42); lane brief in plans/fanout-lanes-2026-11-12.md ("## code-workflows") on branch roadmap.

## Open PRs, read by REST at 00:3x CST Nov 19

| PR | Branch | Live head | State | Handed to runner 10 |
|---|---|---|---|---|
| 2737 judge-replay-corpus | judge-replay-corpus-2 | 057159d3fc0abf9dcb82f142af11a0c64c155574 | open, draft, mergeable unknown | 00:58 CST Nov 14 |
| 2875 main-push-wakes-runner | main-push-wakes-runner | a397280fe972755b35fc1a1e9c31d6069e90eebe | open, draft, dirty vs main | 01:54 CST Nov 14 |
| 2920 main-job-cap-alarm | main-job-cap-alarm-2 | 46bf83830e040365bdb890ec982a3ecac3a42127 | open, draft, dirty vs main | 02:41 CST Nov 14 |
| 2733 mutate-harness-change-timed-run | mutate-harness-change-timed-run-2 | 71a5ad4a7f3fbf1dda857cd1631a4f04cc31bd3f | closed 12:13 CST Nov 14, replaced by PR 3413 (coordinator); branch archived at archive/mutate-harness-change-timed-run-2 | handed in at 50ee413ebc 01:22 Nov 14 |
| 2770 no-ci-starter | no-ci-starter | b1345f772cf3e9ed68623f64fc3b86d851678ecc (GitHub still shows 63e51f3107) | closed 17:43 CST Nov 13 by backlog-drain as an ancestor of 2920 (ledger PR 3154); I did not reopen it | never |

Records and lint at the handed-in heads: PR 2737 rounds FAIL, PASS, PASS, fix check PASS, net positive, lint PASS. PR 2875 rounds FAIL, PASS, FAIL, fix check at f1cde3b157 PASS, net zero, lint PASS 581 s. PR 2920 rounds FAIL, PASS, PASS, net positive, lint PASS 566 s; the record judges the whole diff including PR 2770's commits. All records are PR comments at those heads.

## Done

- PR 2737, 2875, 2920 reviewed, linted and handed in at the heads above. PR 2733 was handed in at 50ee413ebc (lint PASS 362 s, record rounds FAIL, PASS, PASS, fix check PASS, net positive); the coordinator then replaced it with PR 3413.
- PR 2733 cost measured (main run 43564136731, 1 run); PR body states the timed runs fire only for a PR that changes the mutate harness files.
- PR 2920's re-pointed cost pins (31 red at the merge, 0 after, no case weakened) under the coordinator's ruling of 01:57 CST Nov 14.

## Unfinished

- None of the open PRs is merged. After main moved (now bd0759f83c), PR 2875 and PR 2920 read dirty against main. They carry PR 2733's and PR 2770's commits, which now reach main some other way (PR 3413 for 2733's work). Whoever resumes must re-read what main already holds before any merge.
- Notes for PR 2920's five round 3 limits, unfiled so the reviewed head stayed unchanged: (L1) docs/decisions/opt-in-ci-templates-composite.md:33 "No job calls it yet" is false at that head and its "opens no issue" needs the R53 scope; (L2) actions/ci-alarm/action.yml cost text omits the walk; (L3) no-merge-onto-red-main.md:47 narrates history; (L4) the "100 starts" bound is 101; (L5) two test_action.sh labels say "reads its jobs once" where the pin shows 2 reads.
- Leftover `wait_checks` mentions: merge/merge.py WAITS comment, FakeHost.wait_checks in merge/test_merge.py, docs/plans/r42-part2-design.md, docs/plans/align-watchers.md.
- Unfiled nits: PR 2733 shard-stops-unpinned.md says "7 shard cases" (6 plus 1 control), decision line 36 "11 to 16 min"; PR 2737 hooks/test_judge_replay.py lines 28 and 644 "waiting page item 283"; 50 doubled note slugs in docs/debts/notes.md exist on main itself.
- Unstarted steps: bump the two zero pins in skills/project-ops/templates/starter-ci/checks.yml (after PR 2770's code reaches main); wake wiring job in checks.yml (after PR 2920 merges); judge-replay-page-cases (after PR 2737 merges).

## Next step

Read origin/main, then PR 3413 and the backlog-drain ledger (PR 3154) for what already landed. For each open PR: merge main into it with one builder merge commit (a test-author when a test file conflicts, with saved resolutions for non-test files), run `./bin/merge --lane-lint <pr>`, print and post a record at the live head, hand in to runner 10. Order: 2737 first (independent), then 2875, then 2920. Commands: `bin/verdict ./bin/merge --review-record <pr> --head <FULL sha> --kind normal --guard yes --round N:reviewer:MODEL:VERDICT [--fix-check <FULL old head>:reviewer:sonnet:PASS] --net-value <not owed|zero|positive|negative>` with nothing piped after verdict; the body is in the newest /tmp/verdict-*.log.

## Refused acts and cautions

- Not done on purpose: reopening PR 2770 (closed by backlog-drain; coordinator pick b, 01:36 CST Nov 14).
- Refused or blocked, each handled without a workaround: a detached background launch (re-run with run_in_background); builder edits to test files (guard builders-cannot-edit-tests; a test-author took the merge); a record-writer writing in another agent's worktree (outside its scope); `git worktree add` outside the sandbox for a test-author; a scratchpad cleanup of a test-author's scratch copy `mut`.
- Co-author trailers on docs and test commits by writers read Claude Haiku 5.5 (their own model), not Sonnet 5.5.
- No force push, no amend after a push, no merge, no PR opened by this lane in this session.

## Owner rulings I hold

- Items 664 (retry at each Stop), 665 (cap 20, `REPEAT_BATCH`), 666 (check first then mark): owner pick a, 10:57 CST Nov 13; built into PR 2737; triage filed them as own-664-a-retry-each-stop, own-665-a-cap-20, own-666-a-check-then-mark and closes the items after PR 2737 merges.
- R53 (owner 12:58 and 13:07 CST Nov 12, roadmap/rulings/r53.json): each CI or merge alarm wakes the batch runner and opens no GitHub issue; names a red run on main, a job at its cap, a dropped check run; point 4 adds a cap end in an earlier attempt. It covers more than cap ends; what the code does for a red run with no cap end is a separate fact.
- Coordinator rulings: merge order 2733, 2875, 2920 and keep 2770 closed (01:36 CST Nov 14); re-point PR 2920's cost pins to the measured count (01:57 CST Nov 14).
- Owner `override 4h` (15:04 CST Nov 12) expired 19:04 CST Nov 12.

## Agents (names; branch or worktree)

- Builders: ac26b5f256f7a34eb (PR 2733 merge); aaf8993b4d7601fca (PR 2737 merge); a9e69d7a01127690b (no-ci-starter b1345f772c); a99f860f11b1da200 (mpwr-merge, PR 2875 5bf6035f01); a5015b2425a08416b (stopped, nothing pushed); a3fedb75e665218c2 (lane-merge-cap2, aborted, nothing pushed); a04359350136863b2 (lane-merge-cap2d, pushed PR 2920 46bf83830e).
- Test-authors: ab56511681424cf48 (lane-merge-cap2b, f65871eacb, local); a3e48d0c104159857 (lane-merge-cap2c, ab99212bbd, local).
- Record-writers: a8aaa3ff06f6c164e (PR 2875 docs, f1cde3b157); ae92f65fb43d65921 (PR 2875 notes, a397280fe9); ad523aa91931ef17f (lane-merge-cap2b-md, a969aceae6, local).
- Reviewers: a22d9779efa96520a (PR 2770 round 3 FAIL, b1345f772c); a2f3a9d76f44dfd18 (PR 2875 round 3 FAIL); accee61fb2904fc1b (PR 2875 fix check PASS); a3c76f8297b22b3f2 (PR 2920 round 3 PASS).
- All worktrees are under /home/user/claude-settings/.claude/worktrees/agent-<id>. No agent is running. No servers, pids or ports.
