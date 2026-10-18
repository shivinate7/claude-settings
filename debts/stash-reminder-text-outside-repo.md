# The harness reminder tells a worker to push a tagged stash entry

- **What.** The harness worktree reminder still tells a worker to push a tagged entry. The guard now denies that path outright, not asks. The reminder text is not in this repository.
- **Where.** The harness worktree reminder, outside this repository. The deny path is in `hooks/guard_shared_tree.py`.
- **Decision.** `stash-stack-is-a-shared-subject` (the stash stack is a shared subject).
- **Retire.** The harness drops the stash push step from the reminder. Then the deny path has no worker to hit.
