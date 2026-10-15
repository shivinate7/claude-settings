# The records heal-wait stop paths have no test

- **What.** After a heal, the merge waits for checks again. No test covers its stop paths: red checks on the merge commit, a stale page after the wait, a second heal, and a push to main during the wait. No test pins that the Drops-lines trailer names only `docs/records.md`.
- **Where.** The heal-wait block in `merge/merge.py`; `merge/test_merge.py`.
- **Decision.** `records-index-at-merge` (one records index page, rebuilt at merge time).
- **Retire.** One case per stop path and one for the trailer text. Lane records-heal-scope.
