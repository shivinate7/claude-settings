# A merge through the GitHub button leaves a stale records page

- **What.** The merge tool rebuilds the records page before it merges. A merge through the GitHub button, or by auto-merge, does not run the tool, so the page on main can be stale. Only the check on a push to main finds it, and the next merge through the tool heals it.
- **Where.** `merge/merge.py` (`rebuild_records`) and the `--check` mode of `lint/hook_catalog.py`, which waives a stale records page on a pull request run.
- **Decision.** The owner ruling of 2026-10-14, 13:18 CDT: the records page is rebuilt at merge time. No decision entry holds it yet.
- **Retire.** A job on each push to main rewrites the page and opens a pull request when it differs. Or a branch rule refuses a merge that did not use the tool. A case merges by hand and shows the page healed.
