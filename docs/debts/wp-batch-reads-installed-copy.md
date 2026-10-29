# Batch page check reads the installed copy, not main

- **What.** `stale_pages.py` batch mode (no `--page`) compares each live page with the `page.html` installed at session start, not with claude-settings main. A batch that merges a new `page.html` mid-session can then call an old page current. Single-page mode reads `origin/main`, but a local `origin/main` that was not fetched since session start can be old too.
- **Where.** `skills/waiting-page/stale_pages.py` batch mode, and skill `waiting-page` ("Update a repo's pages").
- **Decision.** `questions-go-to-owner` (who asks the owner and how; bullet "The page runs main's code").
- **Retire.** Batch mode reads the same main template as `--page`, with its tests able to run where CI has no `origin/main`. A test shows a page built from an older `page.html` called behind when the installed copy is that older file.
