# The merge tool runs the whole catalog generator in every repo

- **What.** The merge tool runs `lint/hook_catalog.py`, which also builds the hook catalog. A repo root with `hooks/`, `skills/` or `mods/` and no `settings.json` makes the merge refuse. A repo with `settings.json` gets an unasked `docs/catalog.md` in its merge commit.
- **Where.** The rebuild calls in `merge/merge.py`; `lint/hook_catalog.py`.
- **Decision.** `records-index-at-merge` (one records index page, rebuilt at merge time).
- **Retire.** The merge tool runs a records-only mode. Tests show both repo shapes merge and change only `docs/records.md`. Lane records-heal-scope.
