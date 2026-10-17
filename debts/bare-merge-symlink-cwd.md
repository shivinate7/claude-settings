# A symlinked cwd skips the bare-merge ask

- **What.** `uses_merge_tool` walks up the path as written. A cwd that is a symlink from outside the repo into it finds no `.git`, so a bare `gh pr merge` is allowed with no ask.
- **Where.** `uses_merge_tool` in `hooks/guard_merge.py`.
- **Decision.** `bare-merge-asks` (a bare gh pr merge asks when the repo uses the merge tool).
- **Retire.** Resolve the cwd with `realpath` before the walk, with a test case.
