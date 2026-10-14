# The records-page heal can commit conflict markers

- **What.** In a repo with no record folders, a hand-written `docs/records.md` that both sides edited stays as it is: the generator writes nothing. The heal then commits the page with its conflict markers, and the Drops-lines trailer excuses that path from the silent-undo check.
- **Where.** The heal in `merge/merge.py`; `if records:` in `lint/hook_catalog.py`.
- **Decision.** `records-index-at-merge` (one records index page, rebuilt at merge time).
- **Retire.** After the rebuild, the merge stops when the page still holds a conflict marker. A test pins it. Lane records-heal-scope.
