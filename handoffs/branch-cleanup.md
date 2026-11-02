# Handoff: lane branch-cleanup

Session: lane branch-cleanup (claude-settings). Coordinator: session_013NEJL2pASwRjgJDnsvnpNe. Wound down on owner instruction, 2026-11-02 12:31 CST.

## Goal and rulings

- Owner, 2026-11-02 10:41 CST, "Clean up branches" (fb-1041-3). Coordinator brief: four tasks, below.
- Owner ruling, 10:41 CST: the branch count joins the batch pace numbers (rule `reports-batch-pace-numbers`).
- Owner ruling, 10:41 CST: `worktree-agent-*` branches never reach origin.
- Lane ruling, 2026-11-02 12:03 CST: a push to `archive/worktree-agent-*` stays allowed, because rule `shared-trees-archive-then-delete` pushes there. Recorded in decision `agent-branch-never-pushed`.

## State

- Branch `branch-cleanup`, head c2fc5ebf. No PR opened yet. Review round 1 done (reviewer, haiku): fix; its fixes are in 0c7f515c.
- `branch-cleanup-records` (583e1dbd) and `branch-cleanup-tests` (d5f45dce) are merged into `branch-cleanup`. Delete both once the lane merges.
- Remote branches: 240 at 10:41 CST, 258 after the archive pushes, 277 at 12:43 CST (other lanes push too).
- Archive pushes, each checked by sha: archive/batch-40, archive/batch-44, archive/batch-61, archive/batch-63c, archive/batch-63e, archive/batch-64d, archive/batch-oct27j, archive/installer-spine, archive/guard-time-budget-tests, archive/guard-time-budget, archive/live-pin-b, archive/sweep-fast, archive/wt-reap-delay, archive/audit-prose-trees-merge, archive/map-skill-jsx-scan, archive/hook-if-filters, archive/stop-blocks-live-tasks, archive/claude/project-thread-x5hnku, archive/claude/project-thread-rqwx3m, archive/claude/project-thread-ld0jcg. archive/batch-38, archive/batch-39 and archive/worktree-agent-a159a691f176f3cbc already held their branch's tip.

## Done

- Task 1 and 2: docs/plans/briefs/branch-cleanup-mac-deletes.md, 136 branches (113 on main by patch, 23 archived), one leased `git push` for the Mac. The coordinator holds the path; nothing is deleted yet.
- Task 3 cause: agents/*.md told each agent to push its own branch, `worktree-agent-<id>`. Fixed: push only `HEAD:<brief branch>`. Guard rule `agent-branch-push` in hooks/guard_push_delete.py and hooks/guard.py; decision docs/decisions/agent-branch-never-pushed.md. Demo red then green in a throwaway repo (builder report, script at the lane's scratchpad, demo.sh). 19 PUSHAGENT cases, 11 mutants all killed (at f90bad76).
- Task 4: root CLAUDE.md, rule `reports-batch-pace-numbers` now has five numbers; number five is `git ls-remote --heads origin | wc -l`.

## Next

1. Builder (sonnet): merge origin/main into `branch-cleanup`. Only hooks/guard_push_delete.py conflicts. Keep main's `_push_parse`, `_push_dest`, `push_destinations`; drop the branch's `_push_destinations`; in `push_verdict`, after the delete line, add: when not a delete, for each spec not starting `:`, resolve it with `_push_dest`, and return `AGENT_PUSH_RULE` when it starts with `AGENT_BRANCH_PREFIX`. Then run the push-delete family tests, hooks/mutate_guard.py, `ci-job checks --lint`, `check_silent_undo --strict`. Builders may not edit hooks/test_guard.py; it already merges clean.
2. Review round 2 (reviewer, Round 2 of 3 marker).
3. Open a draft PR; send its number, head and verdict to batch runner 7 (session_013NEJKyjt96cx7d1uCdtb8U) and the coordinator.
4. Owner's Mac session runs the delete command after merge; check the count afterwards.

## Open questions

- Reviewer asked whether an agent with no brief branch should keep commits local only. The lane read the owner's 10:41 ruling as yes; the decision says so. Owner: coordinator to confirm.
- docs/records.md is stale on the branch ("four pace numbers"); the merge tool rebuilds it.

## Left by agents, not pushed

Nothing. Each agent pushed its work; local `worktree-agent-*` branches hold no unpushed commit beyond what is on `branch-cleanup`.
