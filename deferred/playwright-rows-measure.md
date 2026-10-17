# A measure of the Playwright guard rows

**What waits.** A measure of whether the Playwright rows in hooks/test_guard.py still earn
their place. These are the PLAYWRIGHT_BROWSERS_PATH set forms (decision
playwright-browsers-path) and the PLAYWRIGHT_INSTALL_DENY table (decision
playwright-install-once).

**Owner ruling, 2026-10-16.** Deferred until Mac testing. The rows stay until then.

**Why it waits.** The incidents behind both rules happened on a Mac. A measure taken on
Windows cannot show whether the rules still stop a real mistake.

**What keeps it from being lost.** This file.

**Trigger.** A session runs Playwright on a Mac.
