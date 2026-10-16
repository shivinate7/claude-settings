# A previous-folder move before an ask step has no known target

- **What.** `cd ~-`, `Set-Location -` and `Set-Location +` count as harmless leads. The guard names no real folder for them, so it judges the ask step in the folder the shell stands in. A shared-tree deny can then become an ask. Measured on the lane head: each form counts as a harmless lead.
- **Where.** `harmless_lead` in `hooks/guard.py`. `_segment_cd_target` in `hooks/guard_core.py` returns None for `-`, and the literal `~-` or `+` for the other two.
- **Decision.** `ask-steps-run-alone`, a step that asks the owner runs alone.
- **Retire.** The three previous-folder forms count as steps, so a chain with them denies. A row in `hooks/test_guard.py` shows each form denies when chained with a shared-tree step, as the `cd -` row does.
