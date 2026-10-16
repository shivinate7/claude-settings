# Outside claude-settings, a standalone check excuses a page drop by trailer only

- **What.** In a repo whose upstream has no `lint/hook_catalog.py`, a standalone run of the check has no generator, so the page excuse never passes. The merge tool passes its own generator, so its runs do compare the page. In a standalone run, the `Drops-lines` trailer is the only excuse. Any non-empty reason excuses the page, with no check against the generator.
- **Where.** `lint/check_silent_undo.py`, `generated_page` (lines 491-523). The generator is imported from the checker's own folder (line 499). The merge tool passes its generator at `merge/merge.py` line 171, and writes the trailer at `merge/merge.py` lines 736 and 774.
- **Decision.** `records-index-at-merge` (one records index page, rebuilt at merge time). Its "Holes, named" section names this gap.
- **Retire.** Either such repos get `lint/hook_catalog.py` on their upstream. Or the check accepts no page trailer in a repo without the generator. A test in `lint/test_check_silent_undo.py` covers a hand-written trailer in a repo with no generator. It shows red on the current code and green after the fix.
