# The skill rows phrases match any cell

- **What.** The check matches the two phrases anywhere on the row line. It does not limit the match to the second cell.
- **Where.** `lint/check_skill_model_rows.py`.
- **Decision.** `subagent-model-cap` (the subagent model cap, and its skill rows check).
- **Retire.** Match the phrases in the second cell only. A fixture with the phrase in the first cell fails.
