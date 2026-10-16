# The silent-undo check hides why the records page failed

- **What.** When the records page generator fails, is missing, or reports a problem, the silent-undo check reports only "hunk reversed" for `docs/records.md` and discards the generator's stderr. The generator run also has no timeout.
- **Where.** `lint/check_silent_undo.py`, `generated_page` (lines 491-518; the generator run at lines 510-512 captures stderr and sets no timeout, and the return at line 512 gives no reason). The "hunk reversed" text is set in `reversals` (line 467).
- **Decision.** `records-index-at-merge` (one records index page, rebuilt at merge time). Its "Holes, named" section names this gap.
- **Retire.** `generated_page` returns the generator's failure text (exit code, first stderr line, or a timeout), and `check` prints it on the page finding. A test in `lint/test_check_silent_undo.py` shows it red on the current code and green after the fix: a generator that exits 1 with a message, and one that runs past the timeout.
