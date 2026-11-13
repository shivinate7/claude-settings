# The Playwright guard rows are not measured

**What.** Unmeasured: whether the Playwright rows in the guard suite (family `kill`, `tests/guard/`) still stop a real mistake. They are the set forms of `playwright-browsers-path` and the `PLAYWRIGHT_INSTALL_DENY` table of `playwright-install-once`. The incidents were on a Mac, so a Windows measure cannot show it.

**Where.** `tests/guard/`, family `kill`: `PLAYWRIGHT_SET_DENY` and `PLAYWRIGHT_INSTALL_DENY`.

**Decision.** `playwright-browsers-path`, a command may not set the Playwright browser path.

**Retire.** Measure when a session runs Playwright on a Mac. Closed when each row is kept or dropped on that measure.

## Ruling

Owner, 2026-10-16: the rows stay until a session runs Playwright on a Mac.
