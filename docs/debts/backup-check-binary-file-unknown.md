# The backup check reads every file as text, so a binary file turns CI red

**What.** `lint/check_waiting_copy_backup.py` calls `read_text` on each file under `skills/`, `hooks/`, `lint/` and `bin/` before it picks the file's kind. A binary file there (an image, say) makes the check print `unknown` and exit 2, so CI goes red though nothing reads the copy. The tree holds no such file today (round 3 review of step `waiting-copy-backup-only`).

**Where.** `lint/check_waiting_copy_backup.py`, the read before `kind_of` (round 3 review put it at lines 517-518).

**Decision.** `waiting-page-one-store`.

**Retire.** Pick the kind by file name first and read only the files of a scanned kind. Add a case with a binary file in a scanned folder that exits 0, red first.
