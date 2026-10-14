# Stash -a passes an ignored-only tree

- **What.** `git stash -a` and `git stash --all` pass the guard over a tree that holds only ignored files. Git stashes those files, and the guard never reads them.
- **Where.** `_tree_subject` in `hooks/guard_shared_tree.py` reads `git status --porcelain` without `--ignored`. A push with `-a` or `--all` reaches it, because those options name no action word.
- **Decision.** `stash-stack-is-a-shared-subject`: a stash push reads the working tree, and a call that names no action word is a push.
- **Retire.** The push read includes ignored files when `-a` or `--all` is named. A test row gives that call the verdict a dirty tree gets. The row fails on the current code before the fix.
