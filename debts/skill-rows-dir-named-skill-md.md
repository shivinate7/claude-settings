# A directory named SKILL.md counts as a skill

- **What.** A directory named `SKILL.md` counts as a skill.
- **Where.** The skill listing in `lint/check_skill_model_rows.py`.
- **Decision.** `subagent-model-cap` (the subagent model cap, and its skill rows check).
- **Retire.** Count only files named `SKILL.md`. A fixture with a directory of that name is not counted.
