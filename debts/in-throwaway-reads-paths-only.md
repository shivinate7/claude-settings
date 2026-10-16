# The throwaway-cwd check reads paths only

- **What.** `in_throwaway` judges path text, not the repo git acts on. So `git --git-dir=/tmp/x/.git merge -q t` with a real cwd, `env -C <real> git commit` from a temp cwd, and a linked worktree under temp pass as throwaway. The silent-write rule then allows a write in a real repo.
- **Where.** `in_throwaway` in `hooks/guard_core.py`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** `in_throwaway` resolves the git dir and work tree that the command acts on, and a guard test denies the three forms above.
