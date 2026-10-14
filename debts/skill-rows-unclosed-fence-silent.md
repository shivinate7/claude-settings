# An unclosed fence hides rows without naming it

- **What.** An unclosed fence or comment hides every later row. The output says no row, and does not name the fence. The check fails visibly, never silently.
- **Where.** `lint/check_skill_model_rows.py`.
- **Decision.** `subagent-model-cap` (the subagent model cap, and its skill rows check).
- **Retire.** Name the open fence in the output. A fixture with an unclosed fence shows its name.
