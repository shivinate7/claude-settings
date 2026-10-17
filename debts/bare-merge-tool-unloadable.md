# A merge tool that will not load denies the bare merge it was the recovery for

- **What.** When `merge/merge.py` cannot load, the head read is unknown and merge-checks denies a bare `gh pr merge` before the bare-merge ask runs. The ask never reaches the owner.
- **Where.** `merge_gate` in `hooks/guard_merge.py` and the merge-checks deny in `hooks/guard.py`.
- **Decision.** `bare-merge-asks` (a bare merge in a merge-tool repo asks).
- **Retire.** An unloadable merge tool in a merge-tool repo asks instead of denying, and a case in `hooks/test_guard.py` pins it. Owner decision: it turns a main refusal into an ask.
