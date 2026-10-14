# Stash help flags are refused as a push

- **What.** `git stash -h` and `git stash --help` are refused over a dirty tree. Git prints help and changes nothing, so the refusal is a false alarm.
- **Where.** `stash_action` in `hooks/guard_shared_tree.py`. A help flag takes no value, so the option loop ends with no action word, and the function returns `push`.
- **Decision.** `stash-stack-is-a-shared-subject`: a call that names no action word is a push, judged on the working tree.
- **Retire.** `stash_action` gives a help flag its own verdict, which is allow. A test row allows `git stash -h` and `git stash --help` over a dirty tree. The row fails on the current code before the fix.
