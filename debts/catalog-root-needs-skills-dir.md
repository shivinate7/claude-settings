# A settings root with hooks/ and no skills/ crashes the catalog

- **What.** `skill_names` lists `skills/` with no check that the folder exists. A settings root that has `hooks/` and no `skills/` gets a `FileNotFoundError` traceback from the catalog render. The merge tool no longer runs the catalog (`--records-only`), so only a hand run and the `--check` gate reach it.
- **Where.** `skill_names` at `lint/check_skill_model_rows.py:68`, called from `lint/hook_catalog.py`.
- **Decision.** `records-index-at-merge` (one records index page, rebuilt at merge time). Its "Holes, named" section names the gap.
- **Retire.** A root with no `skills/` gets an empty list, and a test pins it.
