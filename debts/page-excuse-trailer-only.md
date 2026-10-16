# Outside claude-settings, only a trailer excuses a page drop

- **What.** In a repo whose upstream has no `lint/hook_catalog.py`, the generator run for the records page fails, so the page excuse never passes. The `Drops-lines` trailer from the merge tool is then the only excuse. Any non-empty reason excuses the page, with no check against the generator.
- **Where.** `lint/check_silent_undo.py`, `generated_page` (lines 491-518). The generator is imported from the checker's own folder (line 498). The merge tool writes the trailer at `merge/merge.py` lines 736 and 774.
- **Decision.** `records-index-at-merge` (one records index page, rebuilt at merge time). Its "Holes, named" section names this gap.
- **Retire.** Either such repos get `lint/hook_catalog.py` on their upstream. Or the check accepts no page trailer in a repo without the generator. A test in `lint/test_check_silent_undo.py` covers a hand-written trailer in a repo with no generator. It shows red on the current code and green after the fix.
