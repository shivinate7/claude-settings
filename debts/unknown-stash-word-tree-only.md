# An unknown stash word is judged on the tree only

- **What.** An unknown stash word is read as a push, so the guard judges it on the working tree only. A future git action that takes an entry off the stack would pass over a clean tree. That holds even when another session's entry is on the stack.
- **Where.** `stash_action` and `stash_takes_the_stack` in `hooks/guard_shared_tree.py`. `stash_action` returns `push` for a word that is not in `STASH_ACTIONS`. `stash_subject` reads a push against the tree.
- **Decision.** `stash-stack-is-a-shared-subject`: the stash stack is a shared subject. Its Holes section names this gap.
- **Retire.** Judge an unknown word on both sides. Refuse it when the tree is dirty, or when the stack is non-empty. Check: a test row refuses a made-up stash word over a clean tree that holds a stack entry. A second row refuses it over a dirty tree. Both rows fail on the current code before the fix.
