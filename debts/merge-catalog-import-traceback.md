# A broken catalog module stops the merge tool with a traceback

- **What.** `merge/merge.py` imports `lint/hook_catalog.py` at start, with no guard. A broken module prints a traceback and no clear line, and it blocks the tool that would land its own fix.
- **Where.** The import at the top of `merge/merge.py`.
- **Decision.** `records-index-at-merge` (one records index page, rebuilt at merge time).
- **Retire.** A blocked import prints one clear line and exits non-zero. A test pins it. Lane records-heal-scope.
