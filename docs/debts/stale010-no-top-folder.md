# A cite into another repo or library fails the dead-name check

**What.** STALE010 has no top-folder filter, so `(mypkg/x.py foo)` in a src-layout repo, or a cite into another library such as `(django/db/models.py Model)`, fails "file absent at head". Other repos pin ste-lint, so they meet it. Claude writes these cites in normal work. <!-- ste-disable-line STALE010 -->

**Where.** lint/stale_cites.py `dead_name_cites`.

**Decision.** record-cites-live-code (claims about code cite live code names).

**Retire.** STALE010 skips a cite whose first folder is no top folder of the tracked tree, the same test STALE003 uses (the `tops` set in lint/stale_cites.py `scan_tree`), and a case in `lint/test_stale_cites.py` shows a cite into an untracked top folder gives no STALE010.
