# Handoff: lane archive-sweep-runs-per-merge

Step: archive-sweep-runs-per-merge. Coordinator: session_013NEJL1gw6EdrSyvHkTUEx6.

## State
- Cause found (read, Nov 13 22:45 CST): no merge handed the runner the idle-lane list. On main only `merge --idle-lanes --live FILE` prints it (merge/merge.py `idle_lanes`). The live file on origin/roadmap went stale after batch 132 (readAt 10:40:15 CST). Runner 10 ran the pass after none of its merges.
- Fix built: PR #3383 (head 268a449e54f4c98120d9a748ac262d4b99658350, branch archive-list-at-merge-b). Closed, not merged; carried by another session (owner 2026-11-18 10:27 CST). It replaced #3365 (closed). It supersedes #3108.
- Reviews: round 1 FAIL (haiku, c8739ea61), round 2 PASS (sonnet, f4941de80), round 3 PASS, net value positive (sonnet, e3cf44a29). `merge --lane-lint 3383` PASS at the head. Not run locally: full merge/test_merge.py.
- Unmeasured: hooks/test_mutate_shared.py ShardTests.test_no_shard_runs_all failed once at lint (file not in diff; 5 of 5 pass locally).

## Not mine, left alone
- #2817 and #2848 belong to lane archive-flow (session_013NEJKzCV3NzW5wxzNQ6fWU).
- Step report-says-archived-count (the "Archived: N" report guard) is filed by triage; no lane started.

## Nothing unpushed
All work is on origin at archive-list-at-merge-b (268a449e5). This file is the only addition on the archive branch.
