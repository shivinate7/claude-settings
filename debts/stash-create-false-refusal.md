# git stash create is refused over a non-empty stack

- **What.** `git stash create` falls outside the stash tree actions, so it reads as a take. The guard denies it over a non-empty stack. The false refusal is unmeasured against real use of `create` piped into `store`.
- **Where.** `stash_takes_the_stack` and `STASH_TREE_ACTIONS` in `hooks/guard_shared_tree.py`.
- **Decision.** `stash-stack-is-a-shared-subject` (the stash stack is a shared subject). `stash-push-is-clone-wide` (stash push is clone-wide).
- **Retire.** Run `create` piped into `store` in a real session with a non-empty stack. Then pin the verdict in a test, or add the action to the list.
