# The skill rows check does not limit fence indent

- **What.** In the check, a line of 4 spaces, then a fence mark, inside a fence closes it. A row inside that fence then counts. This gives a false green. A cheap fix breaks fences nested in lists.
- **Where.** `lint/check_skill_model_rows.py`.
- **Decision.** `subagent-model-cap` (the subagent model cap, and its skill rows check).
- **Retire.** Limit the fence indent in a way that keeps fences nested in lists. A fixture with an indented fence mark goes red on the current code.
