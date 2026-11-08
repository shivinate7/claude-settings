# A test-author's merge commit reads as a builder's

- **What.** `own_changes` counts every `commit (merge)` in a worktree's HEAD reflog as the agent's own. A test-author that commits a mixed merge leaves resolved test files that a builder in the same worktree is then refused for (`builder-diff`), and the undo route cannot clear it: the files already match HEAD.
- **Where.** `own_changes` and `ENTRY_OWN` in `hooks/guard.py`; the lane flow that hands one worktree from test-author to builder.
- **Decision.** `builders-cannot-edit-tests` (builders cannot edit tests).
- **Retire.** The guard judges only commits the current agent made, or each role gets its own worktree. A case in `hooks/test_guard.py` shows a builder allowed after a test-author's merge commit in the same worktree. Fix: step:merge-commit-role-scope.
