# Waiting-page checks read only the first account's link

- **What.** `live_pages` calls `waiting_page(root)` with no account, so it returns only the first link of each repo's waiting-page entry. `stale_pages.py` takes its page list from `live_pages`. A waiting page in another account is never read or checked.
- **Where.** `lint/layout.py`, `live_pages` and `waiting_page`. `skills/waiting-page/stale_pages.py`, which reads the list.
- **Decision.** `waiting-data-in-repo` (git is each artifact's home). Its owner ruling of 2026-11-15 13:16 CST ("i think A") sets the per-account registry these reads should use.
- **Retire.** Closed when `live_pages` reads each account's link, and a case in `skills/waiting-page/test_stale_pages.py` shows a page in a second account read and checked, red on the current code.
