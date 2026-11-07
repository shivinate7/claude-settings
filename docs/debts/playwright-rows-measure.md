# The Playwright guard rows are not measured

**What.** Unmeasured: whether the Playwright rows in `hooks/test_guard.py` still stop a real mistake. They are the set forms of `playwright-browsers-path` (no command sets the browser path) and the `PLAYWRIGHT_INSTALL_DENY` table of `playwright-install-once` (one Playwright install). The incidents were on a Mac, so a Windows measure cannot show it.

**Where.** `hooks/test_guard.py`.

- **Decision.** `none`.

**Retire.** Measure when a session runs Playwright on a Mac. Closed when each row is kept or dropped on that measure.

## Ruling

Owner, 2026-10-16: the rows stay until a session runs Playwright on a Mac.
