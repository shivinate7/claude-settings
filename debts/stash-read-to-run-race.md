# A tree or stack changes after the guard reads it

- **What.** An empty tree or an empty stack still passes. A session that dirties the tree, or pushes a stack entry, between the guard's read and the command's run is not covered.
- **Where.** The read-then-run gap in `hooks/guard_shared_tree.py`, for the push and take arms.
- **Decision.** `stash-stack-is-a-shared-subject` (the stash stack is a shared subject). `stash-push-is-clone-wide` (stash push is clone-wide).
- **Retire.** Re-read the subject at the moment of the command, or name the window as a limit. A test that changes the tree between the read and the run goes red on the current code.
