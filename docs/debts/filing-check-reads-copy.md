# The filing check reads the waiting copy as a live source

**What.** The filing check counts the item numbers the waiting copy holds, with one `git grep` of its `items/` folder on origin's record branch. The copy is a backup, and the page database is the one store, so the check can judge a filing against a copy that lags the database. The backup check lets it through by name, as the one reader outside `export_page.py`. An owner pick (undoable): exempt it now, and rule later whether to move the read to the database.

**Where.** `hooks/feedback_guard.py` `Homes.filed_numbers`. The exemption is the `ALLOWED` entry in `lint/check_waiting_copy_backup.py`.

**Decision.** `waiting-page-one-store` (the page database is the one store; git is a timely backup).

**Retire.** Move the filing check's read to the database, or rule the read stays. Then delete the `ALLOWED` entry, so `lint/test_check_waiting_copy_backup.py` shows no reader left.
