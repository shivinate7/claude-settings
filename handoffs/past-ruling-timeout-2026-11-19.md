# Handoff: lane past-ruling-timeout (2026-11-19 00:30 CST)

- Slug: past-ruling-timeout. Role: lane. Parent: coordinator; triage session_013NEJKzCzoWhfP8FMCPtQU6; runner 10 session_013NEJL2f1YCYsvLdpFqtWP3.
- Branch: `past-ruling-run-log` (origin). Head 7b0802508f2b872b1731cbbbccf98545bfe240c2.
- Name clash: `origin/past-ruling-timeout` is an older lane's unmerged work (9 commits, 2026-11-08). Left alone; flagged to triage and coordinator.
- Open PR: 2910, draft, head 7b0802508, base main fccff95e6 when read at 00:28 CST Nov 19. Not merged. CI result unknown to this lane (not read).

## Done
- One writer `record_judge_run` in hooks/call_judge.py: one `measured` guard.log line per model call (ms, chars, outcome; candidates for past-ruling). Rules `judge-run` and `past-ruling-run`. No line when no process starts.
- Reader: lint/guard_log_report.py `--rule past-ruling-run|judge-run` (count, median, max ms, max chars, timeouts). Default read skips these lines.
- report_guard.py diff: +5 lines. Red tests first (test-author), green after (builder). Review round 1 FAIL (4 defects fixed), round 2 PASS.
- Notes filed in docs/debts/notes.md (5 lines, including the open limit read).
- Triage filed #2910 on steps past-ruling-timeout (stays open) and judge-timeout-retries-once (doing).

## Unfinished
- PAST_RULING_TIMEOUT stays 60 s: unmeasured. After a week of run lines, read `python3 lint/guard_log_report.py --rule past-ruling-run --days 7`, then set the limit or cut the candidate list.
- PR 2910 not marked ready, not merged. Main moved on since 2deb827ad; a merge of main into the branch may be needed (standing grant: batch runner).

## Next step
Runner 10 or a new lane: merge main into past-ruling-run-log, read CI, mark ready by the merge tool, merge. Then the 7-day measure.

## Refused acts
- Push to `origin/past-ruling-timeout` (not mine, not tried). Hook `pointer-head` refused a branch switch in the main checkout; a worktree was used.
- Several hooks refused git forms with cd or -C into another worktree; plain commands in the own worktree worked.

## Owner rulings held
None. Coordinator widened scope at 13:36 CST Nov 12 (one log for both steps). Owner order via coordinator 00:19 CST Nov 19: wind down.

## Agents (all finished; worktrees under .claude/worktrees)
- test-author a085854d6027f20d0, branch worktree-agent-a085854d6027f20d0, c65901ef3
- builder a1150b75cd36cba00, branch worktree-agent-a1150b75cd36cba00, 40033cbe4
- reviewer a844a3b383b863056 (round 1, no worktree kept)
- test-author ae0e93e2638cf279a, branch worktree-agent-ae0e93e2638cf279a, dda6e434a
- builder af9bc4f12dea7f9b8, branch worktree-agent-af9bc4f12dea7f9b8, c1f39a012
- reviewer ad892c747d4548b65 (round 2, no worktree kept)

All of that work is already in the PR branch by cherry-pick.
