# The bare-merge ask reads the folder's stamp, not the repo named by -R

- **What.** `gh pr merge -R other/repo` in a merge-tool folder asks, and in a plain folder it allows silently, whatever the named repo uses.
- **Where.** `uses_merge_tool` in `hooks/guard_merge.py` and its call in `hooks/guard.py`.
- **Decision.** `bare-merge-asks` (a bare merge in a merge-tool repo asks).
- **Retire.** The ask follows the repo named by `-R`, and a case in `hooks/test_guard.py` pins it.
