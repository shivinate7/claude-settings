# The cite-by-id rule does not read a gh pr merge subject

- **What.** The cite-by-id rule does not read a `gh pr merge` subject. The lane-by-slug rule does.
- **Where.** The cite-by-id rule in `hooks/guard.py`.
- **Decision.** `lane-by-slug` (a lane is named by its branch slug, not a session number).
- **Retire.** A `gh pr merge` subject that names a record path is refused by cite-by-id, and a case pins it.
