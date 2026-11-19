# Handoff: lane spawn-marker-skip-fences (step spawn-guard-marker-any-line)

Written 2026-11-19 00:25 CST. Repo shivinate7/claude-settings. Session session_013NEJL2PQvDorgDZsKeSyfn (lane; coordinator session_013NEJL1gw6EdrSyvHkTUEx6).

## Where the work is
- Slug: spawn-marker-skip-fences. Work branch: `spawn-marker-skip-fences-2`, head a14d2e2d07a16d67a4f06a0a539e00c4bc3a2876, pushed.
- Open PR: #3339, draft, base `model-layout-to-table` (PR #3286, head 3c7354ad2c88, draft, held set). #3339 head a14d2e2d0, mergeable clean.
- Closed PR: #3324 (old branch `spawn-marker-skip-fences`, head c5d3057d9, pushed; replaced because a pushed commit lacked a Red-run trailer).
- Commits on #3339 over #3286: 4de009792 tests (Red-run trailer), 9704993c3 fix, 7b1943f8c notes, a14d2e2d0 lint fixes (Red-run: none).

## Done
- `marker_scan` line-start rows (Round/Try N of 3) skip lines inside ``` fences (`unfenced_lines`, hooks/guard.py); one toggle shared with `review_guard_marked`. First-line rows unchanged. Fixes the haiku reviewer's false refusal. Decision text (agent-model-cap.md) and shared_names.py comment updated.
- Red tests: tests/guard/s40805-role-model.py, 6 of 13 red on base 3c7354ad2 (test-author haiku).
- Round 1: reviewer sonnet PASS on 9704993c3. Record posted on #3339, comment 6871481739, read back (head a14d2e2d0).
- Notes filed: marker-odd-fence-hides, marker-fence-kinds (docs/debts/notes.md).
- Triage struck the builder half of the step (no guard reads a builder's marker).

## Unfinished
- Lane-lint on a14d2e2d0 is FAIL on one job: Mutation verdict fixture suite, `test_no_shard_runs_all` (thread-order flake). My diff does not touch it. Fix is PR #3149, merged to main 2026-11-14 05:01 UTC (23:01 CST Nov 13).
- Coordinator ruling (23:02 CST Nov 13): do not merge main into #3339. The held-set combine takes newest main once; then re-run `merge --lane-lint 3339` and ask `merge --review-record` for the record at the new head. If stale or missing, coordinator orders a fresh round 1.
- `merge --reviewed` reads "no lint" for a14d2e2d0.

## Next step
When the held-set combine head exists: `~/.claude/bin/verdict ~/.claude/bin/merge -C <main checkout> --lane-lint 3339` (background, about 15 min), then the record, then tell the coordinator when lint reads PASS. After the lane merge-tool-audit-fixes lands, a green all-jobs-passed rollup replaces the lint (owner ruling 21:01 CST Nov 13).

## Refused acts
- `merge --review-record` and `merge --lane-lint` refuse a pipe after `verdict`; run them bare. `git worktree add` by hand was refused once to the test-author, and succeeded for me.

## Owner rulings and orders held
- Owner order 00:19 CST Nov 19, via coordinator: write handoff, push archive branch, stop. This file is that handoff.
- Rulings read in the work: own-r3-reviewer-sonnet-high (owner 2026-11-13 14:05 CST): a real round-3 Opus reviewer is refused with "use sonnet", never lifted.
- Coordinator picks (undoable): route (a), no main merge into #3339; flake belongs to step mutate-shard-test-order-race.
- Triage pick (undoable): builder half struck from the step.

## Agents (all finished; none running)
- test-author haiku, id a420f92c1330f3587, branch `worktree-agent-a420f92c1330f3587`, commit dfc6f748e (unpushed, local worktree .claude/worktrees/agent-a420f92c1330f3587).
- builder sonnet, id a6a66343511c0214e, branch `worktree-agent-a6a66343511c0214e`, commit af0f4f508 (unpushed, local worktree .claude/worktrees/agent-a6a66343511c0214e). Both commits were cherry-picked into the lane branch, so nothing is lost.
- reviewer sonnet, id a2037f1e321e2b0de, round 1 PASS, no branch, worktree gone.

## Scheduled check-ins
- trig_014KL9eWALG4u5cPnz1aTDMS fired and is spent. No open check-in.
