# The hand-made worktree guard misses a path built from a loop variable

**What.** Guard rule `hand-made-worktree` refuses `git worktree add /tmp/x <ref>`. It let through `for c in A B; do git worktree add -q --detach /tmp/claude-0/wt-$c $c; done` (lane batch-local-checks-match-ci, 2026-11-06 15:20 CST, in normal work). That made two trees by hand outside the tool worktrees.

**Where.** `hooks/guard.py`, the `hand-made-worktree` check (the path read for a `worktree add` call).

**Decision.** `lanes-start-in-tool-worktrees` (a lane works only in a tool-made worktree).

**Retire.** A case in `hooks/test_guard.py` for that `for` loop command, red on main, green after the fix.
